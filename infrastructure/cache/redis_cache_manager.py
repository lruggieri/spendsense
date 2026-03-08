"""
Redis-based cache manager for TransactionService instances.

This module provides a Redis-backed cache for TransactionService objects,
enabling cache sharing across multiple Flask workers and processes.
This solves the multi-device/multi-worker cache consistency issues that
existed with in-memory dictionaries.
"""

import logging
import pickle
from typing import Optional

import redis

logger = logging.getLogger(__name__)


class RedisCacheManager:
    """
    Manages caching of TransactionService instances in Redis.

    Features:
    - Shared cache across all Flask workers/processes
    - Automatic TTL (Time To Live) for cache entries
    - Graceful fallback when Redis is unavailable
    - Pickle serialization for complex objects
    """

    # Cache version - increment this when service structure changes to invalidate old caches
    CACHE_VERSION = 2  # v2: Added groups support

    def __init__(
        self,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 0,
        default_ttl: int = 1800,
    ):
        """
        Initialize Redis cache manager.

        Args:
            redis_host: Redis server hostname
            redis_port: Redis server port
            redis_db: Redis database number (0-15)
            default_ttl: Default time-to-live for cache entries in seconds (default: 1800 = 30 minutes)
                        Special values: 0 or negative = cache never expires
        """
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.redis_db = redis_db
        self.default_ttl = default_ttl
        self._redis_client: Optional[redis.Redis] = None
        self._redis_available = True

        # Try to connect to Redis
        self._connect()

    def _connect(self):
        """Establish connection to Redis server."""
        try:
            self._redis_client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                db=self.redis_db,
                decode_responses=False,  # We need binary mode for pickle
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            # Test connection
            self._redis_client.ping()
            self._redis_available = True
            logger.info(f"Successfully connected to Redis at {self.redis_host}:{self.redis_port}")
        except (redis.ConnectionError, redis.TimeoutError) as e:
            self._redis_available = False
            logger.info(f"Failed to connect to Redis: {e}")
            logger.info(
                f"Cache will be disabled. Service will create fresh instances for each request."
            )

    def _get_cache_key(self, user_id: str) -> str:
        """
        Generate Redis cache key for a user's service instance.
        Includes cache version to invalidate old caches when service structure changes.

        Args:
            user_id: User ID

        Returns:
            Redis key string
        """
        return f"service_cache:v{self.CACHE_VERSION}:{user_id}"

    def get(self, user_id: str):
        """
        Retrieve cached TransactionService for a user.

        Args:
            user_id: User ID

        Returns:
            TransactionService instance if found in cache, None otherwise
        """
        if not self._redis_available:
            return None

        try:
            import time

            cache_key = self._get_cache_key(user_id)

            t0 = time.time()
            cached_data = self._redis_client.get(cache_key)
            redis_get_time = (time.time() - t0) * 1000

            if cached_data:
                data_size_mb = len(cached_data) / 1024 / 1024
                logger.info(f"Retrieved {data_size_mb:.2f} MB from Redis in {redis_get_time:.2f}ms")

                # Deserialize from pickle
                t1 = time.time()
                service = pickle.loads(cached_data)  # nosec B301 - data is from trusted internal Redis storage
                unpickle_time = (time.time() - t1) * 1000

                logger.info(f"Unpickling took {unpickle_time:.2f}ms")
                logger.info(f"Cache HIT for user {user_id}")
                return service
            else:
                logger.info(f"Cache MISS for user {user_id} (checked in {redis_get_time:.2f}ms)")
                return None

        except (redis.ConnectionError, redis.TimeoutError) as e:
            logger.info(f"Error reading from cache: {e}")
            return None
        except (pickle.UnpicklingError, EOFError) as e:
            logger.info(f"Error deserializing cached data: {e}")
            # Delete corrupted cache entry
            self.invalidate(user_id)
            return None

    def set(self, user_id: str, service, ttl: Optional[int] = None):
        """
        Store TransactionService in cache.

        Args:
            user_id: User ID
            service: TransactionService instance to cache
            ttl: Time-to-live in seconds (None = use default_ttl, 0 or negative = never expire)
        """
        if not self._redis_available:
            return

        try:
            import time

            cache_key = self._get_cache_key(user_id)
            ttl = ttl if ttl is not None else self.default_ttl

            # Serialize with pickle
            t0 = time.time()
            serialized_data = pickle.dumps(service)
            pickle_time = (time.time() - t0) * 1000
            data_size_mb = len(serialized_data) / 1024 / 1024
            logger.info(f"Pickling took {pickle_time:.2f}ms, size: {data_size_mb:.2f} MB")

            # Store in Redis with or without TTL
            t1 = time.time()
            if ttl <= 0:
                # TTL of 0 or negative means never expire - use SET without expiration
                self._redis_client.set(cache_key, serialized_data)
                redis_set_time = (time.time() - t1) * 1000
                logger.info(
                    f"Cached service for user {user_id} in {redis_set_time:.2f}ms (TTL: NEVER EXPIRES)"
                )
            else:
                # Positive TTL - use SETEX with expiration
                self._redis_client.setex(cache_key, ttl, serialized_data)
                redis_set_time = (time.time() - t1) * 1000
                logger.info(
                    f"Cached service for user {user_id} in {redis_set_time:.2f}ms (TTL: {ttl}s)"
                )

        except (redis.ConnectionError, redis.TimeoutError) as e:
            logger.info(f"Error writing to cache: {e}")
        except pickle.PicklingError as e:
            logger.info(f"Error serializing service: {e}")

    def invalidate(self, user_id: Optional[str] = None):
        """
        Invalidate cache entry for a specific user or all users.

        Args:
            user_id: User ID to invalidate, or None to clear all cache entries
        """
        if not self._redis_available:
            return

        try:
            if user_id:
                # Invalidate specific user
                cache_key = self._get_cache_key(user_id)
                deleted = self._redis_client.delete(cache_key)
                if deleted:
                    logger.info(f"Invalidated cache for user {user_id}")
                else:
                    logger.info(f"No cache entry found for user {user_id}")
            else:
                # Invalidate all service cache entries
                pattern = "service_cache:*"
                keys = self._redis_client.keys(pattern)
                if keys:
                    self._redis_client.delete(*keys)
                    logger.info(f"Invalidated {len(keys)} cache entries")
                else:
                    logger.info(f"No cache entries to invalidate")

        except (redis.ConnectionError, redis.TimeoutError) as e:
            logger.info(f"Error invalidating cache: {e}")

    def is_available(self) -> bool:
        """
        Check if Redis is available.

        Returns:
            True if Redis is connected and available, False otherwise
        """
        return self._redis_available

    def get_stats(self) -> dict:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        if not self._redis_available:
            return {"available": False}

        try:
            pattern = "service_cache:*"
            keys = self._redis_client.keys(pattern)

            # Get TTL for each key
            ttls = {}
            for key in keys:
                ttl = self._redis_client.ttl(key)
                user_id = key.decode("utf-8").replace("service_cache:", "")
                ttls[user_id] = ttl

            return {"available": True, "total_entries": len(keys), "entries": ttls}
        except (redis.ConnectionError, redis.TimeoutError) as e:
            logger.info(f"Error getting stats: {e}")
            return {"available": False, "error": str(e)}

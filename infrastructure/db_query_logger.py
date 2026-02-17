"""
Database query logger utility.

Provides wrappers for sqlite3 cursor methods to log all SQL queries.
"""

import sqlite3
import time
import logging
from typing import Any, Tuple, List, Optional

logger = logging.getLogger(__name__)


def log_query(query: str, params: Optional[Any] = None, duration_ms: Optional[float] = None):
    """
    Log a SQL query with its parameters and execution time.

    Args:
        query: SQL query string
        params: Query parameters (tuple, list, or dict)
        duration_ms: Query execution time in milliseconds
    """
    # Clean up whitespace in query for better display
    clean_query = ' '.join(query.split())

    # Build log message
    log_parts = []

    if duration_ms is not None:
        # Color coding for performance:
        # Green < 10ms, Yellow 10-100ms, Red > 100ms
        if duration_ms < 10:
            color = "\033[32m"  # Green
        elif duration_ms < 100:
            color = "\033[33m"  # Yellow
        else:
            color = "\033[31m"  # Red
        reset = "\033[0m"
        log_parts.append(f"{color}[{duration_ms:.2f}ms]{reset}")

    log_parts.append(clean_query)

    if params:
        if isinstance(params, (tuple, list)):
            # Truncate long parameter lists for readability
            MAX_PARAMS_DISPLAY = 5
            if len(params) > MAX_PARAMS_DISPLAY:
                first_few = ", ".join(repr(p) for p in params[:MAX_PARAMS_DISPLAY])
                params_str = f"[{first_few}, ... ({len(params)} total)]"
            else:
                params_str = str(params)
        elif isinstance(params, dict):
            params_str = str(params)
        else:
            params_str = str(params)
        log_parts.append(f"| params: {params_str}")

    logger.debug(" ".join(log_parts))


class LoggingCursor:
    """
    Wrapper around sqlite3.Cursor that logs all queries.
    """

    def __init__(self, cursor: sqlite3.Cursor):
        """
        Initialize the logging cursor wrapper.

        Args:
            cursor: The underlying sqlite3 cursor to wrap
        """
        self._cursor = cursor

    def execute(self, query: str, parameters: Tuple = ()) -> sqlite3.Cursor:
        """
        Execute a query with logging and timing.

        Args:
            query: SQL query string
            parameters: Query parameters

        Returns:
            The cursor (for chaining)
        """
        start_time = time.time()
        result = self._cursor.execute(query, parameters)
        duration_ms = (time.time() - start_time) * 1000
        log_query(query, parameters if parameters else None, duration_ms)
        return result

    def executemany(self, query: str, seq_of_parameters: List[Tuple]) -> sqlite3.Cursor:
        """
        Execute a query multiple times with logging and timing.

        Args:
            query: SQL query string
            seq_of_parameters: Sequence of parameter tuples

        Returns:
            The cursor (for chaining)
        """
        count = len(seq_of_parameters) if isinstance(seq_of_parameters, list) else "?"
        start_time = time.time()
        result = self._cursor.executemany(query, seq_of_parameters)
        duration_ms = (time.time() - start_time) * 1000
        log_query(query, f"[batch of {count} rows]", duration_ms)
        return result

    def fetchone(self):
        """Fetch one row."""
        return self._cursor.fetchone()

    def fetchall(self):
        """Fetch all rows."""
        return self._cursor.fetchall()

    def fetchmany(self, size: int = None):
        """Fetch many rows."""
        return self._cursor.fetchmany(size)

    @property
    def rowcount(self) -> int:
        """Get the row count."""
        return self._cursor.rowcount

    @property
    def lastrowid(self) -> int:
        """Get the last row ID."""
        return self._cursor.lastrowid

    def __getattr__(self, name):
        """Delegate all other attributes to the underlying cursor."""
        return getattr(self._cursor, name)


def get_logging_cursor(conn: sqlite3.Connection) -> LoggingCursor:
    """
    Get a logging cursor from a connection.

    Args:
        conn: SQLite connection

    Returns:
        LoggingCursor instance
    """
    return LoggingCursor(conn.cursor())

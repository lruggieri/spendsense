"""
SQLite implementation of TransactionRepository.

Stores all transactions in a SQLite database with table structure:
- id (TEXT PRIMARY KEY)
- date (TEXT NOT NULL) - stored as 'YYYY-MM-DDTHH:MM:SSZ' in ISO 8601 UTC format
- amount (INTEGER NOT NULL)
- description (TEXT NOT NULL)
- source (TEXT NOT NULL)
- comment (TEXT)
- user_id (TEXT NOT NULL) - for multi-tenancy support
- groups (TEXT) - JSON array of group IDs
- updated_at (TEXT NOT NULL) - last update timestamp in ISO 8601 UTC format
- mail_id (TEXT) - Gmail message ID for email-fetched transactions
- currency (TEXT NOT NULL) - ISO 4217 currency code (e.g., JPY, USD, EUR)
- created_at (TEXT NOT NULL) - timestamp when transaction was fetched/created in ISO 8601 UTC format

Note: Dates are stored in ISO 8601 format with explicit UTC timezone (Z suffix).
"""

import binascii
import json
import logging
import sqlite3
import unicodedata
from datetime import datetime, timezone
from typing import List, Optional, Set, Tuple

from cryptography.exceptions import InvalidTag

from domain.entities.transaction import ENCRYPTED_PLACEHOLDER, Transaction
from domain.repositories.transaction_repository import TransactionRepository
from infrastructure.crypto.encryption import decrypt_field, encrypt_field
from infrastructure.db_query_logger import get_logging_cursor

logger = logging.getLogger(__name__)


class SQLiteTransactionDataSource(TransactionRepository):
    """SQLite-based transaction storage implementation."""

    def __init__(self, db_filepath: str, user_id: str, encryption_key: Optional[str] = None):
        """
        Initialize SQLite datasource.

        Args:
            db_filepath: Path to the SQLite database file
            user_id: User ID for multi-tenancy filtering
            encryption_key: Optional base64-encoded key for field encryption
        """
        self.db_filepath = db_filepath
        self.user_id = user_id
        self._encryption_key = encryption_key
        self._ensure_db_exists()

    def _ensure_db_exists(self):
        """Create database and transactions table if they don't exist."""
        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id TEXT PRIMARY KEY,
                date TEXT NOT NULL,
                amount INTEGER NOT NULL,
                description TEXT NOT NULL,
                source TEXT NOT NULL,
                comment TEXT DEFAULT '',
                user_id TEXT NOT NULL,
                groups TEXT DEFAULT '[]',
                updated_at TEXT NOT NULL,
                mail_id TEXT,
                currency TEXT NOT NULL DEFAULT 'JPY',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                fetcher_id TEXT,
                encryption_version INTEGER NOT NULL DEFAULT 0
            )
        """)

        # Create index on date for faster date range queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_date ON transactions(date)
        """)

        # Create index on source for faster source filtering
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_source ON transactions(source)
        """)

        # Create index on mail_id for efficient deduplication
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_mail_id ON transactions(mail_id)
        """)

        # Add encryption_version column if missing (for existing databases)
        cursor.execute("PRAGMA table_info(transactions)")
        columns = [row[1] for row in cursor.fetchall()]
        if "encryption_version" not in columns:
            cursor.execute("""
                ALTER TABLE transactions
                ADD COLUMN encryption_version INTEGER NOT NULL DEFAULT 0
            """)

        conn.commit()
        conn.close()

    def _encrypt_value(self, value: str) -> str:
        """Encrypt a field value. Caller must check _encryption_key first."""
        if self._encryption_key is None:
            raise RuntimeError("Encryption key required but not set")
        return encrypt_field(str(value), self._encryption_key)

    def _decrypt_text_fields(self, row: tuple, encryption_version: int) -> Tuple[str, str]:
        """Decrypt description and comment from a DB row.

        Returns (description, comment) as plaintext. Falls back to safe
        placeholders on decryption failure or missing key.
        """
        if encryption_version == 0:
            return (
                unicodedata.normalize("NFKC", row[3]),
                row[5] if row[5] else "",
            )

        if not self._encryption_key:
            return (ENCRYPTED_PLACEHOLDER, "")

        try:
            description = unicodedata.normalize(
                "NFKC", decrypt_field(str(row[3]), self._encryption_key)
            )
            comment = decrypt_field(str(row[5]), self._encryption_key) if row[5] else ""
            return (description, comment)
        except (InvalidTag, ValueError, binascii.Error) as e:
            logger.warning("Failed to decrypt field: %s", e)
            return (ENCRYPTED_PLACEHOLDER, "")

    def _parse_date(self, date_str: str) -> datetime:
        """
        Parse date string into datetime object with UTC timezone.
        Expects ISO 8601 format with Z: YYYY-MM-DDTHH:MM:SSZ
        """
        try:
            # Remove Z suffix if present and parse
            date_str_clean = date_str.rstrip("Z")
            dt = datetime.fromisoformat(date_str_clean)
            # Ensure it's timezone-aware (UTC)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError as e:
            raise ValueError(
                f"Unable to parse date '{date_str}': expected ISO 8601 format 'YYYY-MM-DDTHH:MM:SSZ'. Error: {e}"
            )

    def _format_date(self, dt: datetime) -> str:
        """Format datetime object for storage in database as ISO 8601 UTC."""
        # Convert to UTC if timezone-aware, otherwise assume it's already UTC
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc)
        # Return ISO 8601 format with Z suffix (YYYY-MM-DDTHH:MM:SSZ)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    def _row_to_transaction(self, row: tuple) -> Transaction:
        """
        Convert a database row to a Transaction object.

        Args:
            row: Database row tuple with columns:
                (id, date, amount, description, source, comment, groups, updated_at,
                 mail_id, currency, created_at, fetcher_id, encryption_version)

        Returns:
            Transaction object
        """
        # Parse groups JSON (default to empty list if null or invalid)
        groups = []
        if row[6]:
            try:
                groups = json.loads(row[6])
            except json.JSONDecodeError:
                groups = []

        # Handle currency field (default to JPY for backward-compatibility)
        currency = row[9] if len(row) > 9 and row[9] else "JPY"

        # Parse created_at field (fallback to updated_at for backward-compatibility)
        created_at = (
            self._parse_date(row[10]) if len(row) > 10 and row[10] else self._parse_date(row[7])
        )

        # Handle fetcher_id field (nullable, for backward-compatibility)
        fetcher_id = row[11] if len(row) > 11 else None

        # Handle encryption_version (default to 0 for backward-compatibility)
        encryption_version = row[12] if len(row) > 12 else 0

        # Amount is never encrypted (stays a plain integer for DB portability and SQL aggregation)
        amount = row[2]

        # Decrypt description and comment (source is not encrypted — it's a fetcher
        # name like "Sony Bank" used for SQL filtering, not user-authored PII)
        description, comment = self._decrypt_text_fields(row, encryption_version)

        return Transaction(
            id=row[0],
            date=self._parse_date(row[1]),
            amount=amount,
            description=description,
            category="",  # Category will be assigned by classifier
            source=row[4],
            currency=currency,
            category_source=None,  # Will be set during classification
            mail_id=row[8] if len(row) > 8 else None,  # For backward-compatibility
            comment=comment,
            groups=groups,
            updated_at=self._parse_date(row[7]),
            created_at=created_at,
            fetcher_id=fetcher_id,
            encrypted=encryption_version > 0,
        )

    def get_all_transactions(self) -> List[Transaction]:
        """
        Retrieve all transactions from the database.

        Returns:
            List of all Transaction objects
        """
        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        cursor.execute(
            """
            SELECT id, date, amount, description, source, comment, groups, updated_at, mail_id, currency, created_at, fetcher_id, encryption_version
            FROM transactions
            WHERE user_id = ?
            ORDER BY date DESC
        """,
            (self.user_id,),
        )

        transactions = [self._row_to_transaction(row) for row in cursor.fetchall()]

        conn.close()
        return transactions

    def add_transaction(self, transaction: Transaction) -> None:
        """
        Add a single transaction to the database.

        Args:
            transaction: Transaction object to add

        Note:
            Skips if transaction ID already exists
            Sets updated_at to transaction date
        """
        if self.transaction_exists(transaction.id):
            return

        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        try:
            if self._encryption_key:
                enc_desc = self._encrypt_value(transaction.description)
                enc_comment = self._encrypt_value(transaction.comment or "")
                enc_version = 1
            else:
                enc_desc = transaction.description
                enc_comment = transaction.comment
                enc_version = 0
            cursor.execute(
                """
                INSERT INTO transactions (id, date, amount, description, source, comment, groups, user_id, updated_at, mail_id, currency, created_at, fetcher_id, encryption_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    transaction.id,
                    self._format_date(transaction.date),
                    transaction.amount,
                    enc_desc,
                    transaction.source,
                    enc_comment,
                    json.dumps(transaction.groups),
                    self.user_id,
                    self._format_date(transaction.date),
                    transaction.mail_id,
                    transaction.currency,
                    self._format_date(transaction.created_at or datetime.now(timezone.utc)),
                    transaction.fetcher_id,
                    enc_version,
                ),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            # Duplicate ID, skip silently
            pass
        finally:
            conn.close()

    def add_transactions_batch(self, transactions: List[Transaction]) -> int:
        """
        Add multiple transactions to the database in a batch.

        Args:
            transactions: List of Transaction objects to add

        Returns:
            Number of new transactions added (excluding duplicates)

        Note:
            Sets updated_at to transaction date
        """
        existing_ids = self.get_processed_ids()
        new_transactions = [tx for tx in transactions if tx.id not in existing_ids]

        if not new_transactions:
            return 0

        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        try:
            # Use executemany for better performance
            enc_version = 1 if self._encryption_key else 0
            rows = []
            for tx in new_transactions:
                if self._encryption_key:
                    enc_desc = self._encrypt_value(tx.description)
                    enc_comment = self._encrypt_value(tx.comment or "")
                else:
                    enc_desc = tx.description
                    enc_comment = tx.comment
                rows.append(
                    (
                        tx.id,
                        self._format_date(tx.date),
                        tx.amount,
                        enc_desc,
                        tx.source,
                        enc_comment,
                        json.dumps(tx.groups),
                        self.user_id,
                        self._format_date(tx.date),
                        tx.mail_id,
                        tx.currency,
                        self._format_date(tx.created_at or datetime.now(timezone.utc)),
                        tx.fetcher_id,
                        enc_version,
                    )
                )
            cursor.executemany(
                """
                INSERT OR IGNORE INTO transactions (id, date, amount, description, source, comment, groups, user_id, updated_at, mail_id, currency, created_at, fetcher_id, encryption_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                rows,
            )
            conn.commit()
            added_count = cursor.rowcount
        finally:
            conn.close()

        return added_count

    def transaction_exists(self, tx_id: str) -> bool:
        """
        Check if a transaction with the given ID already exists.

        Args:
            tx_id: Transaction ID to check

        Returns:
            True if transaction exists, False otherwise
        """
        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        cursor.execute(
            "SELECT 1 FROM transactions WHERE id = ? AND user_id = ? LIMIT 1", (tx_id, self.user_id)
        )
        exists = cursor.fetchone() is not None

        conn.close()
        return exists

    def get_processed_ids(self) -> Set[str]:
        """
        Get all transaction IDs currently in the database.

        Returns:
            Set of all transaction IDs
        """
        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        cursor.execute("SELECT id FROM transactions WHERE user_id = ?", (self.user_id,))
        ids = {row[0] for row in cursor.fetchall()}

        conn.close()
        return ids

    def get_processed_mail_ids(self, source: Optional[str] = None) -> Set[str]:
        """
        Get all mail IDs currently in the database.

        Args:
            source: Optional source filter (e.g., "Sony Bank", "Amazon")

        Returns:
            Set of all mail IDs (excluding None values)
        """
        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        if source:
            cursor.execute(
                """
                SELECT DISTINCT mail_id
                FROM transactions
                WHERE user_id = ? AND source = ? AND mail_id IS NOT NULL
            """,
                (self.user_id, source),
            )
        else:
            cursor.execute(
                """
                SELECT DISTINCT mail_id
                FROM transactions
                WHERE user_id = ? AND mail_id IS NOT NULL
            """,
                (self.user_id,),
            )

        mail_ids = {row[0] for row in cursor.fetchall()}

        conn.close()
        return mail_ids

    def filter_imported_mail_ids(self, candidate_ids: List[str]) -> Set[str]:
        """Return the subset of candidate_ids that already exist in the DB."""
        if not candidate_ids:
            return set()

        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        # Process in chunks to stay within SQLite variable limit (999)
        result: Set[str] = set()
        for i in range(0, len(candidate_ids), 900):
            chunk = candidate_ids[i : i + 900]
            placeholders = ",".join("?" * len(chunk))
            cursor.execute(
                f"""
                SELECT DISTINCT mail_id
                FROM transactions
                WHERE user_id = ? AND mail_id IN ({placeholders})
            """,
                (self.user_id, *chunk),
            )
            result.update(row[0] for row in cursor.fetchall())

        conn.close()
        return result

    def get_transactions_by_source(self, source: str) -> List[Transaction]:
        """
        Get all transactions from a specific source.

        Args:
            source: Source name (e.g., "Sony Bank", "Amazon")

        Returns:
            List of transactions from that source
        """
        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        cursor.execute(
            """
            SELECT id, date, amount, description, source, comment, groups, updated_at, mail_id, currency, created_at, fetcher_id, encryption_version
            FROM transactions
            WHERE source = ? AND user_id = ?
            ORDER BY date DESC
        """,
            (source, self.user_id),
        )

        transactions = [self._row_to_transaction(row) for row in cursor.fetchall()]

        conn.close()
        return transactions

    def get_distinct_sources(self) -> List[str]:
        """
        Get all distinct transaction sources for the current user.

        Returns:
            List of unique source names, sorted alphabetically
        """
        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        cursor.execute(
            """
            SELECT DISTINCT source
            FROM transactions
            WHERE user_id = ?
            ORDER BY source ASC
        """,
            (self.user_id,),
        )

        sources = [row[0] for row in cursor.fetchall()]

        conn.close()
        return sources

    def update_transaction(
        self,
        tx_id: str,
        date: datetime,
        amount: int,
        description: str,
        comment: str,
        currency: str = "JPY",
    ) -> bool:
        """
        Update all fields of a transaction.

        Args:
            tx_id: Transaction ID to update
            date: New transaction date
            amount: New amount
            description: New description
            comment: New comment text
            currency: ISO 4217 currency code (default: JPY)

        Returns:
            True if transaction was found and updated, False otherwise

        Note:
            Sets updated_at to current UTC time
        """
        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        try:
            # Set updated_at to current UTC time
            current_time = datetime.now(timezone.utc)
            if self._encryption_key:
                enc_desc = self._encrypt_value(description)
                enc_comment = self._encrypt_value(comment)
                enc_version = 1
            else:
                enc_desc = description
                enc_comment = comment
                enc_version = 0
            cursor.execute(
                """
                UPDATE transactions
                SET date = ?, amount = ?, description = ?, comment = ?, currency = ?, updated_at = ?, encryption_version = ?
                WHERE id = ? AND user_id = ?
            """,
                (
                    self._format_date(date),
                    amount,
                    enc_desc,
                    enc_comment,
                    currency,
                    self._format_date(current_time),
                    enc_version,
                    tx_id,
                    self.user_id,
                ),
            )
            conn.commit()
            updated = cursor.rowcount > 0
        finally:
            conn.close()

        return updated

    def get_transaction_count(self) -> int:
        """
        Get the total number of transactions in the database.

        Returns:
            Total transaction count
        """
        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        cursor.execute("SELECT COUNT(*) FROM transactions WHERE user_id = ?", (self.user_id,))
        count = cursor.fetchone()[0]

        conn.close()
        return count

    def get_last_transaction_date(self) -> Optional[datetime]:
        """
        Get the date of the most recent transaction in the database.

        Returns:
            Date of the last transaction, or None if no transactions exist
        """
        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        cursor.execute(
            """
            SELECT date
            FROM transactions
            WHERE user_id = ?
            ORDER BY date DESC
            LIMIT 1
        """,
            (self.user_id,),
        )

        row = cursor.fetchone()
        conn.close()

        if row:
            return self._parse_date(row[0])
        return None

    def get_transactions_by_date_range(
        self, from_date: Optional[datetime] = None, to_date: Optional[datetime] = None
    ) -> List[Transaction]:
        """
        Get transactions within a date range (efficient for large datasets).

        Args:
            from_date: Start date (inclusive)
            to_date: End date (inclusive)

        Returns:
            List of transactions within the date range
        """
        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        query = "SELECT id, date, amount, description, source, comment, groups, updated_at, mail_id, currency, created_at, fetcher_id, encryption_version FROM transactions WHERE user_id = ?"
        params = [self.user_id]

        if from_date or to_date:
            if from_date:
                query += " AND date >= ?"
                params.append(self._format_date(from_date))
            if to_date:
                query += " AND date <= ?"
                params.append(self._format_date(to_date))

        query += " ORDER BY date DESC"

        cursor.execute(query, tuple(params))

        transactions = [self._row_to_transaction(row) for row in cursor.fetchall()]

        conn.close()
        return transactions

    def add_group_to_transaction(self, tx_id: str, group_id: str) -> bool:
        """
        Add a group to a transaction.

        Args:
            tx_id: Transaction ID
            group_id: Group ID to add

        Returns:
            True if group was added, False if transaction doesn't exist or group already present

        Note:
            Updates updated_at to current UTC time
        """
        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        try:
            # Get current groups
            cursor.execute(
                """
                SELECT groups FROM transactions
                WHERE id = ? AND user_id = ?
            """,
                (tx_id, self.user_id),
            )

            row = cursor.fetchone()
            if not row:
                return False

            # Parse current groups
            groups = []
            if row[0]:
                try:
                    groups = json.loads(row[0])
                except json.JSONDecodeError:
                    groups = []

            # Add group if not already present
            if group_id in groups:
                return False

            groups.append(group_id)

            # Update transaction with new groups and updated_at
            current_time = datetime.now(timezone.utc)
            cursor.execute(
                """
                UPDATE transactions
                SET groups = ?, updated_at = ?
                WHERE id = ? AND user_id = ?
            """,
                (json.dumps(groups), self._format_date(current_time), tx_id, self.user_id),
            )

            conn.commit()
            return cursor.rowcount > 0

        finally:
            conn.close()

    def remove_group_from_transaction(self, tx_id: str, group_id: str) -> bool:
        """
        Remove a group from a transaction.

        Args:
            tx_id: Transaction ID
            group_id: Group ID to remove

        Returns:
            True if group was removed, False if transaction doesn't exist or group wasn't present

        Note:
            Updates updated_at to current UTC time
        """
        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        try:
            # Get current groups
            cursor.execute(
                """
                SELECT groups FROM transactions
                WHERE id = ? AND user_id = ?
            """,
                (tx_id, self.user_id),
            )

            row = cursor.fetchone()
            if not row:
                return False

            # Parse current groups
            groups = []
            if row[0]:
                try:
                    groups = json.loads(row[0])
                except json.JSONDecodeError:
                    groups = []

            # Remove group if present
            if group_id not in groups:
                return False

            groups.remove(group_id)

            # Update transaction with new groups and updated_at
            current_time = datetime.now(timezone.utc)
            cursor.execute(
                """
                UPDATE transactions
                SET groups = ?, updated_at = ?
                WHERE id = ? AND user_id = ?
            """,
                (json.dumps(groups), self._format_date(current_time), tx_id, self.user_id),
            )

            conn.commit()
            return cursor.rowcount > 0

        finally:
            conn.close()

    def add_group_to_transactions_batch(self, tx_ids: List[str], group_id: str) -> int:
        """
        Add a group to multiple transactions in a batch.

        Args:
            tx_ids: List of transaction IDs
            group_id: Group ID to add

        Returns:
            Number of transactions updated

        Note:
            Updates updated_at to current UTC time for each updated transaction
        """
        if not tx_ids:
            return 0

        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        try:
            updated_count = 0
            current_time = datetime.now(timezone.utc)

            for tx_id in tx_ids:
                # Get current groups
                cursor.execute(
                    """
                    SELECT groups FROM transactions
                    WHERE id = ? AND user_id = ?
                """,
                    (tx_id, self.user_id),
                )

                row = cursor.fetchone()
                if not row:
                    continue

                # Parse current groups
                groups = []
                if row[0]:
                    try:
                        groups = json.loads(row[0])
                    except json.JSONDecodeError:
                        groups = []

                # Add group if not already present
                if group_id not in groups:
                    groups.append(group_id)

                    # Update transaction with new groups and updated_at
                    cursor.execute(
                        """
                        UPDATE transactions
                        SET groups = ?, updated_at = ?
                        WHERE id = ? AND user_id = ?
                    """,
                        (json.dumps(groups), self._format_date(current_time), tx_id, self.user_id),
                    )

                    if cursor.rowcount > 0:
                        updated_count += 1

            conn.commit()
            return updated_count

        finally:
            conn.close()

    def remove_group_from_transactions_batch(self, tx_ids: List[str], group_id: str) -> int:
        """
        Remove a group from multiple transactions in a batch.

        Args:
            tx_ids: List of transaction IDs
            group_id: Group ID to remove

        Returns:
            Number of transactions updated

        Note:
            Updates updated_at to current UTC time for each updated transaction
        """
        if not tx_ids:
            return 0

        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        try:
            updated_count = 0
            current_time = datetime.now(timezone.utc)

            for tx_id in tx_ids:
                # Get current groups
                cursor.execute(
                    """
                    SELECT groups FROM transactions
                    WHERE id = ? AND user_id = ?
                """,
                    (tx_id, self.user_id),
                )

                row = cursor.fetchone()
                if not row:
                    continue

                # Parse current groups
                groups = []
                if row[0]:
                    try:
                        groups = json.loads(row[0])
                    except json.JSONDecodeError:
                        groups = []

                # Remove group if present
                if group_id in groups:
                    groups.remove(group_id)

                    # Update transaction with new groups and updated_at
                    cursor.execute(
                        """
                        UPDATE transactions
                        SET groups = ?, updated_at = ?
                        WHERE id = ? AND user_id = ?
                    """,
                        (json.dumps(groups), self._format_date(current_time), tx_id, self.user_id),
                    )

                    if cursor.rowcount > 0:
                        updated_count += 1

            conn.commit()
            return updated_count

        finally:
            conn.close()

    def get_transactions_by_group(self, group_id: str) -> List[Transaction]:
        """
        Get all transactions that belong to a specific group.

        Args:
            group_id: Group ID to filter by

        Returns:
            List of transactions that have this group
        """
        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute(
                """
                SELECT id, date, amount, description, source, comment, groups, updated_at, mail_id, currency, created_at, fetcher_id, encryption_version
                FROM transactions
                WHERE user_id = ? AND groups LIKE ?
                ORDER BY date DESC
            """,
                (self.user_id, f'%"{group_id}"%'),
            )

            # Filter for actual group membership (LIKE can have false positives)
            transactions = [
                tx
                for tx in (self._row_to_transaction(row) for row in cursor.fetchall())
                if group_id in tx.groups
            ]

            return transactions

        finally:
            conn.close()

    def migrate_to_encrypted(self) -> int:
        """
        Encrypt all plaintext transactions (encryption_version=0) for this user.

        Requires self._encryption_key to be set.

        Returns:
            Number of rows migrated.
        """
        if not self._encryption_key:
            return 0

        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)
        migrated = 0
        batch_size = 100

        try:
            while True:
                cursor.execute(
                    """
                    SELECT id, description, comment
                    FROM transactions
                    WHERE user_id = ? AND encryption_version = 0
                    LIMIT ?
                """,
                    (self.user_id, batch_size),
                )

                rows = cursor.fetchall()
                if not rows:
                    break

                for row in rows:
                    tx_id, description, comment = row
                    enc_desc = self._encrypt_value(description or "")
                    enc_comment = self._encrypt_value(comment or "")
                    cursor.execute(
                        """
                        UPDATE transactions
                        SET description = ?, comment = ?, encryption_version = 1
                        WHERE id = ? AND user_id = ? AND encryption_version = 0
                    """,
                        (enc_desc, enc_comment, tx_id, self.user_id),
                    )
                    migrated += cursor.rowcount

                conn.commit()
        finally:
            conn.close()

        return migrated

    def migrate_to_plaintext(self) -> int:
        """
        Decrypt all encrypted transactions (encryption_version=1) back to plaintext.

        Requires self._encryption_key to be set to decrypt.

        Returns:
            Number of rows migrated.
        """
        if not self._encryption_key:
            return 0

        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)
        migrated = 0
        batch_size = 100

        try:
            while True:
                cursor.execute(
                    """
                    SELECT id, description, comment
                    FROM transactions
                    WHERE user_id = ? AND encryption_version = 1
                    LIMIT ?
                """,
                    (self.user_id, batch_size),
                )

                rows = cursor.fetchall()
                if not rows:
                    break

                for row in rows:
                    tx_id, enc_desc, enc_comment = row
                    try:
                        plain_desc = decrypt_field(str(enc_desc), self._encryption_key)
                        plain_comment = (
                            decrypt_field(str(enc_comment), self._encryption_key)
                            if enc_comment
                            else ""
                        )
                    except (InvalidTag, ValueError, binascii.Error) as e:
                        logger.warning("Failed to decrypt tx %s during migration: %s", tx_id, e)
                        continue

                    cursor.execute(
                        """
                        UPDATE transactions
                        SET description = ?, comment = ?, encryption_version = 0
                        WHERE id = ? AND user_id = ? AND encryption_version = 1
                    """,
                        (plain_desc, plain_comment, tx_id, self.user_id),
                    )
                    migrated += cursor.rowcount

                conn.commit()
        finally:
            conn.close()

        return migrated

    def remove_group_from_all_transactions(self, group_id: str) -> int:
        """
        Remove a group from all transactions (cascade delete).

        Args:
            group_id: Group ID to remove from all transactions

        Returns:
            Number of transactions updated

        Note:
            Updates updated_at to current UTC time for each updated transaction
        """
        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        try:
            # Get all transactions that have this group
            cursor.execute(
                """
                SELECT id, groups
                FROM transactions
                WHERE user_id = ? AND groups LIKE ?
            """,
                (self.user_id, f'%"{group_id}"%'),
            )

            rows = cursor.fetchall()
            updated_count = 0
            current_time = datetime.now(timezone.utc)

            for row in rows:
                tx_id, groups_json = row

                # Parse groups
                groups = []
                if groups_json:
                    try:
                        groups = json.loads(groups_json)
                    except json.JSONDecodeError:
                        continue

                # Remove group if present
                if group_id in groups:
                    groups.remove(group_id)

                    # Update transaction with new groups and updated_at
                    cursor.execute(
                        """
                        UPDATE transactions
                        SET groups = ?, updated_at = ?
                        WHERE id = ? AND user_id = ?
                    """,
                        (json.dumps(groups), self._format_date(current_time), tx_id, self.user_id),
                    )

                    if cursor.rowcount > 0:
                        updated_count += 1

            conn.commit()
            return updated_count

        finally:
            conn.close()

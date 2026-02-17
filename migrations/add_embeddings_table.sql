-- Migration: Add embeddings cache table
-- This table stores pre-computed embeddings for transaction descriptions
-- to avoid re-encoding on every load

CREATE TABLE IF NOT EXISTS embeddings (
    tx_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,                -- User ID for multi-tenancy
    embedding BLOB NOT NULL,              -- 384 float32 values (1536 bytes)
    description_hash TEXT NOT NULL,       -- SHA256 hash for cache invalidation
    created_at TEXT NOT NULL,             -- ISO timestamp when embedding was computed
    FOREIGN KEY(tx_id) REFERENCES transactions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_embeddings_user_id ON embeddings(user_id);
CREATE INDEX IF NOT EXISTS idx_embeddings_hash ON embeddings(description_hash);
CREATE INDEX IF NOT EXISTS idx_embeddings_created_at ON embeddings(created_at);

-- Runs once when the Postgres volume is first initialized.
-- The Alembic migration also runs CREATE EXTENSION IF NOT EXISTS vector.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

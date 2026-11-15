-- ==============================================================================
-- MIGRATION 003: Composite unique key (user_id, source_url) for multi-user isolation
-- File: migrations/003_multiuser_url_constraint.sql
-- ==============================================================================

-- 1. Remove old global UNIQUE constraint on source_url
ALTER TABLE items DROP CONSTRAINT IF EXISTS items_source_url_key;

-- 2. Add per-user composite UNIQUE constraint: (user_id, source_url)
-- Allows different users to save the same link in their own private database,
-- preventing duplicate entries only within each individual user's records.
ALTER TABLE items ADD CONSTRAINT items_user_id_source_url_key UNIQUE (user_id, source_url);

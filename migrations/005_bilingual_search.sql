-- ==============================================================================
-- MIGRATION 005: Bilingual Full-Text Search (Italian + English)
-- File: migrations/005_bilingual_search.sql
-- ==============================================================================

-- 1. Update search_tsv column to support simultaneous indexing
--    with both 'italian' and 'english' text dictionaries.
--    Enables native stemming across Italian and English technical terms.

ALTER TABLE items DROP COLUMN IF EXISTS search_tsv CASCADE;

ALTER TABLE items ADD COLUMN search_tsv TSVECTOR GENERATED ALWAYS AS (
    to_tsvector('italian', coalesce(title,'') || ' ' || coalesce(summary,'') || ' ' || coalesce(raw_text,'')) ||
    to_tsvector('english', coalesce(title,'') || ' ' || coalesce(summary,'') || ' ' || coalesce(raw_text,''))
) STORED;

-- 2. Recreate GIN index for instant searches
CREATE INDEX IF NOT EXISTS idx_items_search ON items USING GIN(search_tsv);

-- ==============================================================================
-- MIGRATION 004: RPC function search_cars for automotive queries with numeric filters
-- File: migrations/004_search_automotive.sql
-- ==============================================================================

CREATE OR REPLACE FUNCTION search_cars(
    filter_user_id text DEFAULT 'default',
    max_price numeric DEFAULT NULL,
    min_price numeric DEFAULT NULL,
    g21_only boolean DEFAULT false,
    laser_lights boolean DEFAULT false,
    match_limit int DEFAULT 10
)
RETURNS SETOF items
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT *
    FROM items
    WHERE status = 'active'
      AND category = 'Automotive & Annunci Auto'
      AND (filter_user_id = 'all' OR user_id = filter_user_id)
      AND (max_price IS NULL OR (metadata->>'prezzo_eur')::numeric <= max_price)
      AND (min_price IS NULL OR (metadata->>'prezzo_eur')::numeric >= min_price)
      AND (NOT g21_only OR (metadata->>'carrozzeria_generazione') ILIKE '%g21%')
      AND (NOT laser_lights OR (
            metadata->'optional_chiave' ? 'Fari Laser'
            OR (metadata->>'optional_chiave') ILIKE '%laser%'
      ))
    ORDER BY created_at DESC
    LIMIT match_limit;
END;
$$;

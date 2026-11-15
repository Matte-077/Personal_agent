-- ==============================================================================
-- MIGRATION 002: RPC function match_items for semantic vector search
-- File: migrations/002_match_items.sql
-- ==============================================================================

CREATE OR REPLACE FUNCTION match_items (
    query_embedding vector(768),
    match_threshold float DEFAULT 0.3,
    match_count int DEFAULT 5,
    filter_user_id text DEFAULT 'default',
    filter_category text DEFAULT NULL
)
RETURNS TABLE (
    id uuid,
    user_id text,
    title text,
    summary text,
    category text,
    subcategory text,
    tags text[],
    metadata jsonb,
    source_url text,
    confidence numeric,
    created_at timestamp with time zone,
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        items.id,
        items.user_id,
        items.title,
        items.summary,
        items.category,
        items.subcategory,
        items.tags,
        items.metadata,
        items.source_url,
        items.confidence,
        items.created_at,
        1 - (items.embedding <=> query_embedding) AS similarity
    FROM items
    WHERE items.status = 'active'
      AND (items.user_id = filter_user_id OR filter_user_id = 'all')
      AND (filter_category IS NULL OR items.category = filter_category)
      AND (items.embedding IS NOT NULL)
      AND (1 - (items.embedding <=> query_embedding)) >= match_threshold
    ORDER BY items.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

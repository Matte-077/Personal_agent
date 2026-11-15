-- ==============================================================================
-- INITIAL MIGRATION: items table, HNSW vector indices, FTS and RLS
-- File: migrations/001_init.sql
-- ==============================================================================

-- 1. Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Create primary items table
CREATE TABLE IF NOT EXISTS items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT DEFAULT 'default' NOT NULL,
    status TEXT DEFAULT 'active' NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    source_url TEXT UNIQUE,
    source_type TEXT NOT NULL CHECK (source_type IN (
        'instagram', 'mobile_de', 'web_article', 'text_note', 'voice', 'receipt', 'image', 'other'
    )),
    raw_text TEXT,
    category TEXT NOT NULL,
    subcategory TEXT,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    tags TEXT[] DEFAULT '{}',
    metadata JSONB DEFAULT '{}'::jsonb,
    confidence NUMERIC(3,2) DEFAULT 1.00 CHECK (confidence >= 0.00 AND confidence <= 1.00),
    embedding VECTOR(768),
    -- Automatically generated full-text search index
    search_tsv TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('italian', coalesce(title,'') || ' ' || coalesce(summary,'') || ' ' || coalesce(raw_text,''))
    ) STORED
);

-- 3. Relational and JSONB indices for fast filtering
CREATE INDEX IF NOT EXISTS idx_items_category ON items(category);
CREATE INDEX IF NOT EXISTS idx_items_tags ON items USING GIN(tags);
CREATE INDEX IF NOT EXISTS idx_items_metadata ON items USING GIN(metadata);

-- 4. HNSW vector index for fast semantic search (avoids sequential scan)
CREATE INDEX IF NOT EXISTS idx_items_embedding ON items USING hnsw (embedding vector_cosine_ops);

-- 5. GIN index for fast full-text search
CREATE INDEX IF NOT EXISTS idx_items_search ON items USING GIN(search_tsv);

-- 6. Trigger function to auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = timezone('utc'::text, now());
    RETURN NEW;
END;
$$ LANGUAGE 'plpgsql';

DROP TRIGGER IF EXISTS trigger_update_items_updated_at ON items;
CREATE TRIGGER trigger_update_items_updated_at
    BEFORE UPDATE ON items
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- 7. Enable Row Level Security (RLS)
ALTER TABLE items ENABLE ROW LEVEL SECURITY;

-- 8. Access policy for service_role
DROP POLICY IF EXISTS "Service role full access" ON items;
CREATE POLICY "Service role full access" ON items
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

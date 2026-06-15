-- Enable pgvector for Honcho's embeddings (the pgvector image ships the
-- extension; Honcho's own migrations create the tables on first boot).
CREATE EXTENSION IF NOT EXISTS vector;

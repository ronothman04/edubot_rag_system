-- Create crawl_jobs table in Supabase to persist crawler status, statistics, and timestamps
CREATE TABLE IF NOT EXISTS public.crawl_jobs (
  job_id uuid NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
  url character varying(1024) NOT NULL,
  status character varying(50) NOT NULL DEFAULT 'pending', -- pending, crawling, processing, chunking, embedding, completed, failed, paused, cancelled
  current_stage character varying(50) NOT NULL DEFAULT 'queued', -- queued, fetching, extracting, ingesting, chunking, embedding, saving, completed, skipped
  pages_found integer DEFAULT 0,
  pages_processed integer DEFAULT 0,
  pages_skipped integer DEFAULT 0,
  pages_failed integer DEFAULT 0,
  pdfs_found integer DEFAULT 0,
  pdfs_processed integer DEFAULT 0,
  documents_found integer DEFAULT 0,
  documents_processed integer DEFAULT 0,
  chunks_created integer DEFAULT 0,
  embeddings_generated integer DEFAULT 0,
  skipped_urls text[] DEFAULT '{}',
  errors text[] DEFAULT '{}',
  started_at timestamp with time zone DEFAULT now(),
  finished_at timestamp with time zone,
  last_crawl_timestamp timestamp with time zone DEFAULT now()
);

-- Enable RLS for security compliance
ALTER TABLE public.crawl_jobs ENABLE ROW LEVEL SECURITY;

-- Create policy for admins/superadmins to view and manage crawl jobs
CREATE POLICY "Admins can manage crawl jobs" ON public.crawl_jobs
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM public.profiles
      WHERE id = auth.uid() AND role IN ('admin', 'superadmin')
    )
  );

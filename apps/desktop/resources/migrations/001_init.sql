PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  root_path TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL CHECK (status IN ('active', 'archived')) DEFAULT 'active',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS media_assets (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  source_path TEXT NOT NULL,
  display_name TEXT NOT NULL,
  container TEXT NOT NULL,
  duration_sec REAL NOT NULL,
  size_bytes INTEGER NOT NULL,
  selected_audio_stream INTEGER NOT NULL DEFAULT 0,
  extracted_audio_path TEXT,
  probe_json_path TEXT,
  content_hash TEXT,
  created_at TEXT NOT NULL,
  UNIQUE (project_id, source_path)
);
CREATE INDEX IF NOT EXISTS idx_media_assets_project ON media_assets(project_id);

CREATE TABLE IF NOT EXISTS media_streams (
  id TEXT PRIMARY KEY,
  media_id TEXT NOT NULL REFERENCES media_assets(id) ON DELETE CASCADE,
  stream_index INTEGER NOT NULL,
  codec_type TEXT NOT NULL,
  codec_name TEXT NOT NULL,
  duration_sec REAL,
  sample_rate INTEGER,
  channels INTEGER,
  channel_layout TEXT,
  bit_rate INTEGER,
  width INTEGER,
  height INTEGER,
  avg_frame_rate TEXT,
  start_pts REAL,
  start_time_sec REAL,
  disposition_default INTEGER NOT NULL DEFAULT 0,
  tags_json TEXT,
  UNIQUE (media_id, stream_index)
);

CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK (kind IN (
    'analyze', 'preview', 'restore', 'export', 'model_install', 'extract'
  )),
  state TEXT NOT NULL CHECK (state IN (
    'queued', 'preparing', 'running', 'validating',
    'completed', 'failed', 'cancelled', 'interrupted'
  )),
  progress REAL NOT NULL DEFAULT 0 CHECK (progress >= 0 AND progress <= 1),
  result_ref TEXT,
  error_json TEXT,
  payload_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_project_state ON jobs(project_id, state);

CREATE TABLE IF NOT EXISTS artifacts (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  media_id TEXT REFERENCES media_assets(id) ON DELETE SET NULL,
  kind TEXT NOT NULL CHECK (kind IN (
    'extracted_audio', 'stage_audio', 'preview_audio', 'restored_audio',
    'video_proxy', 'analysis_json', 'quality_report', 'other'
  )),
  path TEXT NOT NULL,
  content_hash TEXT,
  stage_id TEXT,
  params_hash TEXT,
  bytes INTEGER,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_artifacts_project ON artifacts(project_id);

CREATE TABLE IF NOT EXISTS analyses (
  id TEXT PRIMARY KEY,
  media_id TEXT NOT NULL REFERENCES media_assets(id) ON DELETE CASCADE,
  job_id TEXT REFERENCES jobs(id) ON DELETE SET NULL,
  schema_version TEXT NOT NULL,
  result_json TEXT NOT NULL,
  result_path TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_analyses_media ON analyses(media_id);

CREATE TABLE IF NOT EXISTS treatment_plans (
  id TEXT PRIMARY KEY,
  analysis_id TEXT NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
  schema_version TEXT NOT NULL,
  preset TEXT NOT NULL CHECK (preset IN ('natural', 'balanced', 'enhanced')),
  plan_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS job_stages (
  id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  stage_id TEXT NOT NULL,
  state TEXT NOT NULL,
  progress REAL NOT NULL DEFAULT 0,
  message TEXT,
  artifact_id TEXT REFERENCES artifacts(id),
  started_at TEXT,
  finished_at TEXT,
  UNIQUE (job_id, stage_id)
);

CREATE TABLE IF NOT EXISTS restoration_runs (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  media_id TEXT NOT NULL REFERENCES media_assets(id) ON DELETE CASCADE,
  analysis_id TEXT NOT NULL REFERENCES analyses(id),
  plan_id TEXT REFERENCES treatment_plans(id),
  job_id TEXT REFERENCES jobs(id) ON DELETE SET NULL,
  mode TEXT NOT NULL CHECK (mode IN ('preview', 'full')),
  settings_json TEXT NOT NULL,
  settings_hash TEXT NOT NULL,
  output_artifact_id TEXT REFERENCES artifacts(id),
  report_json TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_restoration_runs_media ON restoration_runs(media_id);

CREATE TABLE IF NOT EXISTS exports (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  media_id TEXT NOT NULL REFERENCES media_assets(id),
  restoration_run_id TEXT NOT NULL REFERENCES restoration_runs(id),
  job_id TEXT REFERENCES jobs(id) ON DELETE SET NULL,
  output_path TEXT NOT NULL,
  mode TEXT NOT NULL CHECK (mode IN ('video_remux', 'audio_only')),
  container TEXT NOT NULL,
  audio_codec TEXT NOT NULL,
  video_copied INTEGER NOT NULL DEFAULT 0,
  duration_sec REAL NOT NULL,
  sample_count_ok INTEGER NOT NULL DEFAULT 0,
  loudness_json TEXT,
  warnings_json TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS models (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  phase TEXT NOT NULL CHECK (phase IN ('mvp', 'v2', 'v3')),
  optional INTEGER NOT NULL DEFAULT 0,
  license_notice TEXT,
  state TEXT NOT NULL CHECK (state IN (
    'notInstalled', 'downloading', 'verifying', 'installed', 'error'
  )),
  version TEXT,
  installed_at TEXT,
  error_message TEXT
);

CREATE TABLE IF NOT EXISTS model_files (
  id TEXT PRIMARY KEY,
  model_id TEXT NOT NULL REFERENCES models(id) ON DELETE CASCADE,
  relative_path TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  bytes INTEGER,
  UNIQUE (model_id, relative_path)
);

CREATE TABLE IF NOT EXISTS app_settings (
  key TEXT PRIMARY KEY,
  value_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

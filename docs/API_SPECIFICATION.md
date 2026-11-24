# API Specification — AudioRestorer AI

**Status:** Approved planning document  
**Contract sources:** zod (Node domain) + Pydantic v2 / OpenAPI (Python engine)  
**Related:** [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md), [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md)

---

## 1. Overview

Two API surfaces:

1. **Renderer ↔ Main:** typed Electron IPC via `contextBridge` (zod-validated).  
2. **Main ↔ Engine:** HTTP + WebSocket on `127.0.0.1` with per-launch bearer token.

Logical REST-style names from the product brief map to IPC channels; the engine exposes a smaller audio-centric HTTP API.

### Common conventions

- IDs: UUID v4 strings.  
- Timestamps: ISO-8601 UTC.  
- Paths: absolute Windows paths as strings; validated and canonicalized in main.  
- Errors: `{ code, message, details?, retryable }`  
- Schema versioning: `schema_version` on analysis / plan / settings payloads.

---

## 2. Error model

```ts
interface ApiError {
  code: ErrorCode;
  message: string;
  details?: Record<string, unknown>;
  retryable: boolean;
}
```

| Code | Meaning | Retryable |
|------|---------|-----------|
| `VALIDATION_ERROR` | Schema / arg validation failed | false |
| `NOT_FOUND` | Project / job / media missing | false |
| `MEDIA_UNSUPPORTED` | Container/codec not supported | false |
| `MEDIA_CORRUPT` | Decode/probe failure | false |
| `DISK_FULL` | Insufficient space | false |
| `ENGINE_UNAVAILABLE` | Sidecar down | true |
| `ENGINE_CRASH` | Sidecar crashed mid-job | true |
| `CUDA_OOM` | GPU out of memory | true (smaller chunk / CPU) |
| `MODEL_NOT_INSTALLED` | Required model missing | false |
| `CHECKSUM_MISMATCH` | Model download corrupt | true |
| `JOB_CANCELLED` | User cancel | false |
| `SYNC_VALIDATION_FAILED` | Export sample/PTS mismatch | false |
| `STAGE_GUARD_FAILED` | Quality guard exhausted retries | false |
| `PERMISSION_DENIED` | Path outside allowlist | false |
| `INTERNAL` | Unexpected | false |

---

## 3. Shared domain schemas

### 3.1 Project

```ts
interface Project {
  id: string;
  name: string;
  root_path: string;
  created_at: string;
  updated_at: string;
  status: "active" | "archived";
}
```

### 3.2 Media metadata

```ts
interface MediaStream {
  index: number;
  codec_type: "audio" | "video" | "subtitle" | "data" | "attachment";
  codec_name: string;
  duration_sec?: number;
  sample_rate?: number;
  channels?: number;
  channel_layout?: string;
  bit_rate?: number;
  width?: number;
  height?: number;
  avg_frame_rate?: string;
  start_pts?: number;
  start_time_sec?: number;
  disposition_default?: boolean;
  tags?: Record<string, string>;
}

interface MediaAsset {
  id: string;
  project_id: string;
  source_path: string;
  display_name: string;
  container: string;
  duration_sec: number;
  size_bytes: number;
  streams: MediaStream[];
  selected_audio_stream: number;
  extracted_audio_path?: string;
  probe_json_path?: string;
  created_at: string;
}
```

### 3.3 Analysis result

```ts
type Recoverability = "recoverable" | "partial" | "not_recoverable";
type ContentLabel = "speech_dominant" | "music_dominant" | "mixed" | "ambience";

interface TimelineRegion {
  start_sec: number;
  end_sec: number;
  content: { speech: number; music: number; ambience: number };
  label: ContentLabel;
}

interface AnalysisIssue {
  id: string; // e.g. "hum" | "hiss" | "clipping" | "muffled" | "wind" | ...
  severity: number; // 0..1
  confidence: number; // 0..1
  recoverability: Recoverability;
  evidence: Record<string, unknown>;
  regions: { start_sec: number; end_sec: number }[];
  user_message: string;
}

interface AnalysisResult {
  schema_version: "1.0.0";
  id: string;
  media_id: string;
  duration_sec: number;
  sample_rate: number;
  channels: number;
  global_metrics: {
    loudness: {
      integrated_lufs: number;
      lra: number;
      true_peak_dbtp: number;
      momentary_max_lufs?: number;
      short_term_max_lufs?: number;
    };
    crest_factor_db: number;
    clipping_ratio: number;
    stereo: {
      correlation: number;
      lr_balance_db: number;
      polarity_inverted: boolean;
    };
    spectral?: Record<string, number>;
  };
  timeline: TimelineRegion[];
  issues: AnalysisIssue[];
  versions: Record<string, string>;
  created_at: string;
}
```

### 3.4 Treatment plan

```ts
type StageId =
  | "condition"
  | "declip"
  | "hum_notch"
  | "wind_rumble"
  | "denoise_speech"
  | "denoise_music_gate"
  | "dereverb"
  | "separate_remix"
  | "tonal_eq"
  | "stereo"
  | "dynamics"
  | "deess"
  | "loudness"
  | "limiter";

interface PlannedStage {
  id: StageId;
  enabled: boolean;
  reason: string;
  confidence: number;
  params: Record<string, unknown>;
  depends_on: StageId[];
  conflicts_with: StageId[];
}

interface TreatmentPlan {
  schema_version: "1.0.0";
  id: string;
  analysis_id: string;
  preset: "natural" | "balanced" | "enhanced";
  stages: PlannedStage[];
  warnings: string[];
  created_at: string;
}
```

### 3.5 Restoration settings

```ts
interface RestorationSettings {
  schema_version: "1.0.0";
  preset: "natural" | "balanced" | "enhanced";
  strength: number; // 0..1
  music_enhancement: number;
  speech_clarity: number;
  ambience_preservation: number;
  noise_reduction: number;
  bass_balance: number; // -1..1
  treble_recovery: number;
  stereo_width: number; // e.g. 0.5..1.5
  loudness_target_lufs: number; // e.g. -23 | -16 | -14
  module_overrides: Partial<Record<StageId, { enabled?: boolean; params?: Record<string, unknown> }>>;
  model_versions: Record<string, string>;
}
```

### 3.6 Job status

```ts
type JobKind = "analyze" | "preview" | "restore" | "export" | "model_install";
type JobState =
  | "queued"
  | "preparing"
  | "running"
  | "validating"
  | "completed"
  | "failed"
  | "cancelled"
  | "interrupted";

interface JobStageProgress {
  stage_id: string;
  state: JobState;
  progress: number; // 0..1
  message?: string;
}

interface JobStatus {
  id: string;
  project_id: string;
  kind: JobKind;
  state: JobState;
  progress: number; // 0..1
  stages: JobStageProgress[];
  result_ref?: string; // analysis_id | artifact_id | export_id
  error?: ApiError;
  created_at: string;
  updated_at: string;
  started_at?: string;
  finished_at?: string;
}
```

### 3.7 Export result

```ts
interface ExportResult {
  id: string;
  job_id: string;
  output_path: string;
  mode: "video_remux" | "audio_only";
  container: string;
  audio_codec: string;
  video_copied: boolean;
  duration_sec: number;
  sample_count_ok: boolean;
  loudness?: { integrated_lufs: number; true_peak_dbtp: number };
  warnings: string[];
  created_at: string;
}
```

---

## 4. Renderer ↔ Main IPC

Invocation pattern: `window.api.invoke(channel, payload) → Promise<Result>`.  
Events: `window.api.on(channel, handler)` for job progress.

### 4.1 Projects

| Channel | Request | Response |
|---------|---------|----------|
| `projects.create` | `{ name: string, root_path?: string }` | `Project` |
| `projects.list` | `{}` | `Project[]` |
| `projects.get` | `{ id: string }` | `Project` |
| `projects.delete` | `{ id: string }` | `{ ok: true }` |
| `projects.rename` | `{ id: string, name: string }` | `Project` |

### 4.2 Media

| Channel | Request | Response |
|---------|---------|----------|
| `media.import` | `{ project_id: string, source_path: string }` | `MediaAsset` |
| `media.get` | `{ id: string }` | `MediaAsset` |
| `media.selectAudioStream` | `{ id: string, stream_index: number }` | `MediaAsset` |
| `media.extractAudio` | `{ id: string }` | `{ job_id: string }` |

Maps to brief: `POST /api/media/import`.

### 4.3 Analysis

| Channel | Request | Response |
|---------|---------|----------|
| `analysis.start` | `{ project_id: string, media_id: string }` | `{ job_id: string }` |
| `analysis.get` | `{ id: string }` | `AnalysisResult` |

Maps to: `POST /api/analyze`, `GET /api/analyze/{id}`.

### 4.4 Restoration / preview

| Channel | Request | Response |
|---------|---------|----------|
| `plan.get` | `{ analysis_id: string, preset?: string, settings?: Partial<RestorationSettings> }` | `TreatmentPlan` |
| `restoration.start` | `{ project_id, media_id, analysis_id, settings: RestorationSettings, plan_id?: string }` | `{ job_id: string }` |
| `preview.render` | `{ project_id, media_id, analysis_id, settings, start_sec, end_sec }` | `{ job_id: string }` |

Maps to: `POST /api/restoration`, `POST /api/preview`.

### 4.5 Jobs

| Channel | Request | Response |
|---------|---------|----------|
| `jobs.get` | `{ id: string }` | `JobStatus` |
| `jobs.cancel` | `{ id: string }` | `JobStatus` |
| `jobs.list` | `{ project_id: string }` | `JobStatus[]` |
| `jobs.subscribe` | `{ id: string }` | event stream `JobStatus` |

Maps to: `GET /api/jobs/{id}`.

### 4.6 Export

| Channel | Request | Response |
|---------|---------|----------|
| `export.start` | `{ project_id, media_id, restoration_artifact_id, mode, output_path, options }` | `{ job_id: string }` |
| `export.get` | `{ id: string }` | `ExportResult` |

```ts
interface ExportOptions {
  mode: "video_remux" | "audio_only";
  container?: string;
  audio_codec?: "aac" | "flac" | "pcm_f32le" | "pcm_s24le" | "mp3" | "opus" | "alac";
  audio_bitrate_kbps?: number;
  keep_original_audio_track?: boolean; // V2
}
```

### 4.7 Models & settings

| Channel | Request | Response |
|---------|---------|----------|
| `models.list` | `{}` | `ModelInfo[]` |
| `models.install` | `{ model_id: string }` | `{ job_id: string }` |
| `models.remove` | `{ model_id: string }` | `{ ok: true }` |
| `settings.get` | `{}` | `AppSettings` |
| `settings.set` | `Partial<AppSettings>` | `AppSettings` |

```ts
interface ModelInfo {
  id: string;
  name: string;
  phase: "mvp" | "v2" | "v3";
  installed: boolean;
  optional: boolean;
  license_notice?: string;
  size_bytes?: number;
  sha256?: string;
  state: "notInstalled" | "downloading" | "verifying" | "installed" | "error";
}

interface AppSettings {
  device_preference: "auto" | "cuda" | "cpu";
  default_loudness_lufs: number;
  default_preset: "natural" | "balanced" | "enhanced";
  projects_root: string;
  model_store_path: string;
  redact_paths_in_logs: boolean;
  max_vram_mb?: number;
}
```

### 4.8 IPC validation rules

- Reject unknown keys where schemas are strict.  
- Canonicalize and allowlist all filesystem paths.  
- Cap preview duration (e.g. ≤ 120 s) unless user confirms longer.  
- Rate-limit model install to one active download job.

---

## 5. Main ↔ Engine HTTP API

Base URL: `http://127.0.0.1:{port}/v1`  
Header: `Authorization: Bearer {launch_token}`

### 5.1 Health & capabilities

**`GET /v1/health`**

```json
{ "status": "ok", "version": "0.1.0", "uptime_sec": 12.3 }
```

**`GET /v1/capabilities`**

```json
{
  "devices": [{ "id": "cuda:0", "name": "NVIDIA GeForce RTX 3070", "vram_mb": 8192 }],
  "cuda_available": true,
  "installed_models": ["silero_vad", "deepfilternet3", "panns_cnn14", "dnsmos"],
  "max_chunk_sec": 10
}
```

### 5.2 Analyze

**`POST /v1/analyze`**

```json
{
  "job_id": "uuid",
  "audio_path": "D:/.../extracted.wav",
  "sample_rate": 48000,
  "channels": 2
}
```

Response: `{ "job_id": "uuid" }` (async). Result written to agreed path or fetched via job.

**`GET /v1/jobs/{id}`** → engine-local job view (progress, result path, error).

### 5.3 Plan

**`POST /v1/plan`**

```json
{
  "analysis": { "...AnalysisResult..." },
  "preset": "balanced",
  "settings": { "...optional RestorationSettings partial..." }
}
```

Response: `TreatmentPlan` (sync; pure function).

### 5.4 Render (preview or full)

**`POST /v1/render`**

```json
{
  "job_id": "uuid",
  "mode": "preview" | "full",
  "audio_path": "...",
  "output_path": "...",
  "plan": { "...TreatmentPlan..." },
  "settings": { "...RestorationSettings..." },
  "region": { "start_sec": 10, "end_sec": 25 },
  "working_sample_rate": 48000
}
```

- `preview`: require `region`; may add pre-roll internally.  
- `full`: process entire file with checkpoints under `artifact_dir` (optional field).

### 5.5 Job control & events

- **`POST /v1/jobs/{id}/cancel`** → `{ "ok": true }`  
- **`WS /v1/jobs/{id}/events`** → stream:

```json
{ "type": "progress", "progress": 0.42, "stage_id": "tonal_eq", "message": "chunk 8/40" }
{ "type": "warning", "code": "STAGE_SKIPPED", "message": "denoise_speech skipped after guard failure" }
{ "type": "completed", "output_path": "...", "report_path": "..." }
{ "type": "failed", "error": { "code": "CUDA_OOM", "message": "...", "retryable": true } }
```

### 5.6 Models (engine runtime)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/v1/models` | Loaded + available adapters |
| POST | `/v1/models/{id}/load` | Load to device |
| POST | `/v1/models/{id}/unload` | Free VRAM |

Install/download remains a **main-process** concern (checksummed fetch into model store); engine only loads from verified paths.

---

## 6. Mapping brief REST → actual surfaces

| Brief endpoint | Actual |
|----------------|--------|
| `POST /api/projects` | IPC `projects.create` |
| `POST /api/media/import` | IPC `media.import` |
| `POST /api/analyze` | IPC `analysis.start` → engine `POST /v1/analyze` |
| `GET /api/analyze/{id}` | IPC `analysis.get` |
| `POST /api/restoration` | IPC `restoration.start` → engine `POST /v1/render` |
| `GET /api/jobs/{id}` | IPC `jobs.get` (+ engine job mirror) |
| `POST /api/preview` | IPC `preview.render` |
| `POST /api/export` | IPC `export.start` (FFmpeg in main) |
| `GET /api/models` | IPC `models.list` |

---

## 7. Validation and idempotency

- Engine stages are **idempotent** given identical inputs + settings hash → reuse artifact if present.  
- Content-addressed artifact keys: `sha256(input_file + stage_id + params_json + model_versions)`.  
- Preview and full renders never overwrite originals.  
- Export refuses if `sample_count_ok` would be false after verification dry-run checks.

---

## 8. Related documents

- [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md)
- [AUDIO_PIPELINE.md](AUDIO_PIPELINE.md)
- [UI_UX_SPECIFICATION.md](UI_UX_SPECIFICATION.md)

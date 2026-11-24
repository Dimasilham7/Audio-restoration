# Product Requirements — AudioRestorer AI

**Status:** Approved planning document  
**Product:** AudioRestorer AI  
**Platform:** Windows 10/11 desktop  
**Distribution:** Portfolio / open-source, non-commercial (GPL-3.0-or-later)  
**Team assumption:** Solo full-time developer

---

## 1. Product vision

Build a production-oriented Windows desktop application that uses AI and digital signal processing (DSP) to automatically analyze, restore, enhance, and export audio from video or audio files.

The product supports **general audio restoration**, not concert recordings only. It preserves the original video and replaces its audio with the restored result (or exports restored audio alone).

### Core principle

> AI analyzes → diagnoses degradation → recommends treatment → executes AI/DSP restoration → validates quality → user previews and adjusts → exports restored media.

### Product mode

| Attribute | Requirement |
|-----------|-------------|
| Deployment | Desktop, Windows 10/11 |
| Connectivity | Offline / local-first; no mandatory cloud API |
| Acceleration | Local NVIDIA GPU where supported; CPU fallback |
| Scale | Large media files (multi-hour) |
| Auth | No mandatory user registration |
| Interaction | Hybrid: automatic analysis and recommendations, with manual override |

---

## 2. Target users

1. **Content creators** restoring smartphone and camera audio for social or portfolio video.
2. **Hobbyists / archivists** cleaning live music, interviews, and family recordings.
3. **Developers / researchers** evaluating offline restoration pipelines (portfolio audience).

Non-goals for users: broadcast mastering suites, real-time DAW plug-in hosts, cloud SaaS editors.

---

## 3. Input scenarios

The application must handle:

1. Concert and live music recordings.
2. Smartphone recordings with voice-focused audio processing already enabled.
3. Recordings with muffled audio (partially obstructed microphone).
4. Speech and dialogue recordings.
5. Videos with wind, background noise, hum, and hiss.
6. Clipped or distorted audio.
7. Poor tonal balance, low volume, or unbalanced stereo.
8. Mixed content containing speech, music, and environmental ambience.

---

## 4. Functional requirements

### 4.1 Project and media

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-P1 | Create, open, list, and delete local projects | MVP |
| FR-P2 | Import video and audio files into a project | MVP |
| FR-P3 | Probe media (containers, streams, duration, sample rate, channels) | MVP |
| FR-P4 | Select which audio stream to restore when multiple exist | MVP |
| FR-P5 | Keep original media immutable (read-only reference) | MVP |
| FR-P6 | Support interrupted / resumable jobs | MVP |

### 4.2 Analysis and diagnosis

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-A1 | Multi-label analysis: speech/music/mixed probabilities | MVP |
| FR-A2 | Detect muffling, frequency suppression, clipping, distortion | MVP |
| FR-A3 | Detect background noise, wind, hum, hiss | MVP |
| FR-A4 | Detect stereo imbalance, dynamic-range and loudness issues | MVP |
| FR-A5 | Produce a structured diagnosis report with confidences | MVP |
| FR-A6 | Distinguish recoverable vs partial vs not-recoverable issues | MVP |
| FR-A7 | Label restoration vs AI reconstruction clearly | MVP |

### 4.3 Treatment and restoration

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-R1 | Rule-based treatment planner with transparent recommendations | MVP |
| FR-R2 | Execute adaptive DSP chain (EQ, filters, dynamics, loudness) | MVP |
| FR-R3 | Speech-gated enhancement (never apply speech models blindly to music) | MVP |
| FR-R4 | Presets: Natural, Balanced, Enhanced | MVP |
| FR-R5 | User macro controls for intensity and per-domain adjustments | MVP |
| FR-R6 | Inter-stage quality guards with fallback / skip | MVP |
| FR-R7 | Optional music source separation for rebalancing | V2 |
| FR-R8 | Dereverberation | V2 |
| FR-R9 | Generative bandwidth extension (explicitly labeled reconstruction) | V3 |

### 4.4 Preview, A/B, export

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-X1 | Preview restoration on a selectable time range before full render | MVP |
| FR-X2 | Original vs restored A/B comparison (loudness-matched by default) | MVP |
| FR-X3 | Residual / “removed signal” listen mode | MVP |
| FR-X4 | Export restored video (audio replaced, video stream-copied when possible) | MVP |
| FR-X5 | Export restored audio alone (WAV, FLAC, MP3, M4A) | MVP |
| FR-X6 | Preserve A/V sync, duration, relevant metadata | MVP |
| FR-X7 | Optionally keep original audio as disabled secondary track | V2 |

### 4.5 Models and settings

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-M1 | Local model manager (list, install, verify SHA-256, remove) | MVP |
| FR-M2 | Lazy load / unload models; respect VRAM budget | MVP |
| FR-M3 | Application settings (paths, device preference, loudness defaults) | MVP |
| FR-M4 | Optional download of license-ambiguous models with notice | V2 |

---

## 5. Non-functional requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| NFR-1 | Offline-capable; no cloud required for core workflows | MVP |
| NFR-2 | GPU acceleration on NVIDIA (RTX 3070 class); CPU fallback | MVP |
| NFR-3 | Process multi-hour files without loading full float arrays into RAM | MVP |
| NFR-4 | Cooperative cancellation ≤ 2 s at chunk boundaries | MVP |
| NFR-5 | Progress reporting per stage and overall | MVP |
| NFR-6 | Temporary file cleanup on start/exit and after failed jobs | MVP |
| NFR-7 | Electron security: contextIsolation, sandbox, validated IPC | MVP |
| NFR-8 | Logs must not store audio content; optional path redaction | MVP |
| NFR-9 | Dependency pinning with hashes; model checksum verification | MVP |
| NFR-10 | Measurable quality gates (see TESTING_STRATEGY.md) | MVP |

---

## 6. Supported media formats

### Containers / codecs (MVP)

| Format | Role | Notes |
|--------|------|-------|
| MP4 | Video + audio | Primary |
| MOV | Video + audio | |
| MKV | Video + audio | Preferred remux target for odd codecs |
| AVI | Video + audio | Limited; may recommend remux to MKV |
| WAV | Audio | Including RF64 for large files |
| MP3 | Audio | LAME encode for export |
| AAC / M4A | Audio | Native FFmpeg AAC encoder |
| FLAC | Audio | Preferred lossless export |

### Media edge cases (must be designed for)

- Variable frame rate (preserve via stream-copy of video).
- Multiple audio / video streams.
- Audio start offset / PTS.
- Mono, stereo, multichannel (multichannel processing = V2).
- Metadata and chapters preservation.
- Long recordings.
- Corrupted / truncated media (detect and refuse or warn).
- Interrupted processing with resume from stage checkpoints.

---

## 7. Interaction mode (hybrid)

The application must:

1. Automatically analyze input.
2. Automatically select restoration models and processing chains.
3. Generate recommended restoration settings.
4. Allow users to manually adjust restoration intensity and domain controls.
5. Provide original vs restored A/B comparison.
6. Allow preview before full processing.
7. Allow users to approve or modify the result.
8. Support exporting video and audio separately.

---

## 8. Explicit MVP scope

### In scope (MVP)

- Local Electron desktop shell + Python restoration engine sidecar.
- Project management, import, analysis, diagnosis UI.
- Rule-based treatment planner.
- DSP restoration (EQ, notch/hum, wind/rumble HPF, spectral gate for music hiss, dynamics, stereo, loudness, limiter, de-ess for speech).
- Speech-gated DeepFilterNet3 (or equivalent ONNX/CLI path) for speech-dominant regions.
- Silero VAD + audio tagging for content classification.
- Preview segment render + loudness-matched A/B + residual mode.
- Full render with chunked processing, quality guards, cancellation.
- Export video remux (stream-copy video) and audio-only export.
- Model manager for MVP models; first-run Python/runtime provisioning.
- SQLite project/job persistence and crash recovery.
- Evaluation harness + acceptance criteria calibration.

### Out of scope for MVP

- Cloud APIs, accounts, telemetry requiring network (optional update check may exist later).
- Real-time / live streaming restoration.
- DAW plug-in (VST/AU) hosting.
- Batch folder processing UI (CLI batch may exist for eval only).
- Automatic mastering to a reference track (Matchering-style).
- Multichannel surround processing.
- Generative models that invent missing bandwidth or content.
- Mobile / macOS / Linux shipping targets.

---

## 9. Deferred features

### V2

- HTDemucs (optional download + license notice) for music-dominant rebalancing, only if Phase 0 spike shows value.
- WPE dereverberation (`nara_wpe`).
- Advanced declipping (A-SPADE).
- resemble-enhance as alternative speech denoiser.
- Multichannel (5.1) downmix / process / remux.
- Keep original audio as disabled secondary track on export.
- Segment-level parameter automation curves.
- Stronger phone-processed-audio artifact detection.

### V3

- AudioSR / generative bandwidth extension in isolated env, labeled **AI reconstruction**.
- BS-RoFormer (only checkpoints that pass license review).
- ML-based treatment routing trained on labeled diagnosis→plan data.
- Detection of already-processed smartphone audio (musical noise, gating).
- Optional cloud model mirror (still offline-capable).

---

## 10. Success metrics

| Metric | Target (MVP) |
|--------|--------------|
| Sync integrity | Output sample count equals input; zero A/V drift on remux |
| Loudness | Within ±0.5 LU of target; true peak ≤ target + 0.1 dB |
| Do-no-harm | Clean input SI-SDR ≥ 30 dB vs itself after pipeline |
| Speech improvement | PESQ/STOI improve on noisy speech fixtures |
| Hum | ≥ 25 dB suppression with &lt; 0.5 dB change outside notches |
| Reliability | 2 h stereo file completes on 8 GB VRAM / 32 GB RAM without OOM |
| UX preference | Hybrid preferred over original in ≥ 70% blind trials per category |
| Cancellation | Cooperative cancel ≤ 2 s |

---

## 11. Assumptions

1. Users accept GPL-3.0-or-later and will download optional models with separate notices.
2. Development and primary testing occur on Windows 11 with NVIDIA RTX 3070 8 GB.
3. FFmpeg is redistributed under GPL with source offer (gyan essentials or equivalent pinned build).
4. First-run may download a multi-GB CUDA/CPU torch environment into `%LOCALAPPDATA%`.
5. English UI for MVP; i18n deferred.
6. Solo full-time timeline of ~26–32 weeks is acceptable (not an 8-week demo).

---

## 12. Related documents

- [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md)
- [AI_MODEL_EVALUATION.md](AI_MODEL_EVALUATION.md)
- [AUDIO_PIPELINE.md](AUDIO_PIPELINE.md)
- [API_SPECIFICATION.md](API_SPECIFICATION.md)
- [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md)
- [UI_UX_SPECIFICATION.md](UI_UX_SPECIFICATION.md)
- [DEVELOPMENT_ROADMAP.md](DEVELOPMENT_ROADMAP.md)
- [TESTING_STRATEGY.md](TESTING_STRATEGY.md)
- [TECHNICAL_RISKS.md](TECHNICAL_RISKS.md)

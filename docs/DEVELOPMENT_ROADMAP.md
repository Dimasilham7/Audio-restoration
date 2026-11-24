# Development Roadmap — AudioRestorer AI

**Status:** Approved planning document  
**Capacity:** Solo full-time developer  
**Overall estimate:** **26–32 weeks** to MVP packaging (not an 8-week demo)  
**Related:** [PRODUCT_REQUIREMENTS.md](PRODUCT_REQUIREMENTS.md), [TESTING_STRATEGY.md](TESTING_STRATEGY.md), [TECHNICAL_RISKS.md](TECHNICAL_RISKS.md)

---

## 1. Repository structure (target monorepo)

```
audio-restoration/
  apps/desktop/                 # Electron + React + Vite (electron-vite)
    src/main/
    src/preload/
    src/renderer/
  packages/contracts/           # zod schemas + generated OpenAPI types
  engine/                       # uv Python 3.12
    src/audiorestorer_engine/
      api/
      io/
      analysis/
      planning/
      dsp/
      adapters/
      pipeline/
      quality/
    tests/
  eval/                         # harness, manifests (no media in git)
  packaging/                    # electron-builder, model manifest, ffmpeg fetch
  docs/                         # planning docs (this set)
  README.md
  .gitignore
  pnpm-workspace.yaml           # when code lands
  pyproject / engine uv project # when code lands
```

Principle: avoid unnecessary abstraction; grow packages only when duplication appears.

---

## 2. Phase overview

| Phase | Name | Effort | Depends on |
|-------|------|--------|------------|
| P0 | Research & technical validation | 3 wk | — |
| P1 | Python audio restoration POC (CLI) | 2–3 wk | P0 |
| P2 | Analyzer & DSP engine | 5 wk | P1 |
| P3 | AI model integration | 3 wk | P0, P2 |
| P4 | Treatment orchestration | 3 wk | P2, P3 |
| P5 | Electron desktop UI | 5 wk | P4 (can stub earlier) |
| P6 | Preview & export | 3 wk | P5 |
| P7 | Performance optimization | 2 wk | P6 |
| P8 | Packaging & release | 2–3 wk | P7 |

Parallelism note: UI shell (P5) can start after P1 with mocked engine, but full integration waits for P4.

---

## 3. Phase details

### Phase 0 — Research and technical validation

**Objective:** De-risk models, CUDA, licenses, and evaluation before building product code volume.

**Tasks:**

1. Provision Python 3.12 with `uv` on the reference machine; pin torch CUDA wheel; smoke-test GPU.  
2. Spike DeepFilterNet3 via Windows CLI and/or ONNX; compare quality.  
3. Spike HTDemucs on concert fixtures (VRAM, RTF, subjective value).  
4. Choose tagger (PANNs vs EfficientAT vs inaSpeechSegmenter); capture weight licenses.  
5. Build synthetic degradation toolkit skeleton.  
6. Assemble private eval corpus manifests (paths local-only).  
7. Document verified VRAM/RTF numbers; update risk register.

**Dependencies:** Windows machine with RTX 3070; network for downloads.

**Deliverables:**

- `eval/` harness skeleton + corpus manifest format.  
- Phase 0 report notes (can live in TECHNICAL_RISKS updates).  
- Locked decision: DFN integration path; tagger choice; Demucs V2 go/no-go lean.

**Acceptance criteria:**

- Torch CUDA tensor op succeeds on GPU.  
- At least one speech denoise path runs end-to-end on a fixture.  
- License texts for MVP weights filed.  
- Baseline metrics computed for 5+ fixtures.

**Risks:** DFN pip unusable (known) — mitigated by CLI/ONNX; Demucs weights license blocks bundling (already planned).

**Test strategy:** Smoke scripts; not full product tests yet.

**Effort:** 3 weeks.

---

### Phase 1 — Python audio restoration POC

**Objective:** CLI that extracts (via ffmpeg subprocess or pre-extracted WAV), conditions, denoises speech, notches hum, loudness-normalizes, writes WAV.

**Tasks:**

1. Create `engine/` uv project structure.  
2. Implement IO (soundfile RF64-aware).  
3. Implement DC block, resample to 48 kHz, basic hum notch, loudness+limiter.  
4. Integrate DFN adapter (CLI or ONNX) behind interface.  
5. CLI entry: `audiorestorer-engine process --input ... --output ...`.  
6. Length-preservation asserts.

**Dependencies:** P0 DFN path decision.

**Deliverables:** Working CLI POC; unit tests for length/NaN.

**Acceptance criteria:**

- Speech fixture improves DNSMOS/PESQ relative to noisy input.  
- Output length == input length.  
- True peak ≤ −1 dBTP ±0.1 when limiter on.

**Risks:** Resample quality; stereo policy for mono models.

**Test strategy:** pytest on synthetic hum + noise clips.

**Effort:** 2–3 weeks.

---

### Phase 2 — Analyzer and DSP engine

**Objective:** Streaming analyzer + full DSP module set with safe bounds.

**Tasks:**

1. Streaming ebur128 (ffmpeg filter) + spectral feature pipeline.  
2. Detectors: clip, hum, hiss, wind, muffled, stereo, DR/loudness.  
3. Emit `AnalysisResult` JSON.  
4. DSP modules: EQ, HPF/LPF, notches, multiband dyn, expander, de-ess, stereo, spectral gate, Janssen declip.  
5. Golden transfer-function tests for filters.  
6. Property tests: identity-near on clean audio (do-no-harm rough).

**Dependencies:** P1 IO foundations.

**Deliverables:** `analysis/` + `dsp/` packages; schema fixtures.

**Acceptance criteria:**

- Analyzer detects injected hum/clip/hiss on synthetic set with defined TPR/FPR targets (see TESTING).  
- DSP bounds enforced in code.  
- Clean audio SI-SDR ≥ 30 dB through DSP-only mild path.

**Risks:** Detector false positives on music; calibrate thresholds.

**Test strategy:** Synthetic degradations + unit tests.

**Effort:** 5 weeks.

---

### Phase 3 — AI model integration

**Objective:** Production adapters, model manager hooks, VRAM budget.

**Tasks:**

1. Adapter interface: load/unload/process_chunk/latency.  
2. Silero VAD ONNX; DFN; tagger; DNSMOS.  
3. Model manifest + SHA-256 verify utilities (Python + later Node).  
4. Device selection + sequential GPU queue stub.  
5. Chunked OLA harness shared by adapters.

**Dependencies:** P0 choices; P2 timelines for gating.

**Deliverables:** `adapters/` + model manifest schema; integration tests with tiny fixtures.

**Acceptance criteria:**

- Load → process 30 s → unload without VRAM leak (nvidia-smi before/after).  
- Missing model raises `MODEL_NOT_INSTALLED`.  
- Checksum mismatch deletes file and errors.

**Risks:** ONNX op compatibility; Windows path lengths.

**Test strategy:** Adapter contract tests; optional GPU CI later (local).

**Effort:** 3 weeks.

---

### Phase 4 — Treatment orchestration

**Objective:** Rule-based planner, pipeline orchestrator, quality guards, checkpoints.

**Tasks:**

1. Implement `plan(analysis, preset, overrides)`.  
2. Stage graph execution with skip/enable.  
3. Inter-stage guards + milder retry + skip.  
4. Checkpoint artifacts + resume.  
5. FastAPI surface: health, analyze, plan, render, jobs, WS progress.  
6. OpenAPI export for contracts package.

**Dependencies:** P2, P3.

**Deliverables:** End-to-end engine API; planner unit tests; pipeline integration tests.

**Acceptance criteria:**

- Speech+noise routes to gated DFN; music+muffle does not.  
- Guard failure skips stage and returns warning.  
- Cancel stops ≤ 2 s.  
- Resume after kill continues from last stage.

**Risks:** Over-complex stage graph — keep linear ordered list with skip flags.

**Test strategy:** Table-driven planner tests; pipeline on fixtures.

**Effort:** 3 weeks.

---

### Phase 5 — Electron desktop UI

**Objective:** Desktop shell with IPC, supervisor, SQLite, core screens.

**Tasks:**

1. Scaffold electron-vite + React + Tailwind + WaveSurfer.  
2. Main services: projects, media, jobs, settings, engine supervisor.  
3. SQLite migrations per DATABASE_SCHEMA.  
4. Preload bridge + zod validation.  
5. Screens: Welcome, Import, Analysis, Diagnosis, Restoration (basic), Settings, Models (basic).  
6. Security hardening baseline.

**Dependencies:** P4 for real engine; can mock earlier.

**Deliverables:** Runnable desktop app driving local engine.

**Acceptance criteria:**

- Create project → import → analyze → see diagnosis → adjust preset → start restore job.  
- Engine crash shows recoverable error; supervisor restarts.  
- No nodeIntegration; IPC rejects path escape.

**Risks:** Electron build tooling on Windows; better-sqlite3 native rebuilds.

**Test strategy:** Vitest for services; Playwright Electron smoke.

**Effort:** 5 weeks.

---

### Phase 6 — Preview and export

**Objective:** Proxies, A/B UX, remux/export validation.

**Tasks:**

1. Video proxy generation; preview region render.  
2. A/B loudness-matched player + residual mode.  
3. Export video remux + audio-only; metadata/PTS handling.  
4. Post-export verification (sample count, loudness).  
5. Export Center UI.

**Dependencies:** P5.

**Deliverables:** Complete user path to exported file.

**Acceptance criteria:**

- Remux preserves video hash (stream-copy) when codecs allow.  
- Sample count match; no `-shortest` dependency.  
- A/B switch sample-aligned; loudness match default on.

**Risks:** Weird containers (AVI, VFR, offsets) — build matrix tests.

**Test strategy:** Media matrix fixtures; e2e export test.

**Effort:** 3 weeks.

---

### Phase 7 — Performance optimization

**Objective:** Fit 8 GB VRAM / long files; tune chunks; caching; CPU fallback UX.

**Tasks:**

1. Chunk size auto-tune on CUDA OOM.  
2. Artifact cache hits measured.  
3. Streaming analysis memory profile on 2 h file.  
4. Benchmark suite RTF report generation.  
5. UI progress accuracy improvements.

**Dependencies:** P6.

**Deliverables:** Benchmark report; perf budgets documented.

**Acceptance criteria:**

- 2 h stereo file completes without OOM on reference hardware.  
- Cancel ≤ 2 s.  
- Cache hit skips recomputation of identical stage params.

**Risks:** Disk thrashing — keep stage retention policy.

**Test strategy:** Perf jobs in `eval/`; memory sampling scripts.

**Effort:** 2 weeks.

---

### Phase 8 — Packaging and release

**Objective:** NSIS installer, first-run provisioning, licenses, local crash logs.

**Tasks:**

1. electron-builder Windows NSIS.  
2. Bundle uv + FFmpeg (+ checksums) + model manifest.  
3. First-run wizard: runtime + CUDA/CPU torch + MVP models.  
4. Third-party license page + FFmpeg source offer.  
5. Crash recovery UX polish; logging redaction.  
6. Tag `v0.1.0-mvp` documentation freeze.

**Dependencies:** P7.

**Deliverables:** Installable build; release checklist.

**Acceptance criteria:**

- Clean Windows 11 VM (or second profile) installs and runs sample restore offline after provisioning.  
- Optional models not bundled; Demucs notice path works if enabled later.  
- Uninstall leaves user projects unless opted in.

**Risks:** Installer size; SmartScreen reputation (portfolio: document sideload).

**Test strategy:** Fresh-install checklist; smoke restore.

**Effort:** 2–3 weeks.

---

## 4. Post-MVP

### V2 (indicative 8–12 weeks after MVP)

- HTDemucs optional (if P0 spike positive).  
- WPE dereverb; A-SPADE; resemble-enhance.  
- Multichannel; secondary original audio track.  
- Segment automation curves.

### V3

- AudioSR isolated worker; BS-RoFormer cleared checkpoints; ML routing; phone-processed detection.

---

## 5. Prioritized implementation backlog

1. Pinned Python/Node environment + repo scaffolding.  
2. Evaluation harness + synthetic degradations.  
3. FFmpeg probe / extract / remux with sync verification.  
4. Streaming analyzer.  
5. Hum, declip, EQ, loudness DSP.  
6. DeepFilterNet adapter.  
7. Treatment planner.  
8. Engine FastAPI + WS progress.  
9. Electron shell + SQLite + supervisor.  
10. Diagnosis UI.  
11. Preview + A/B.  
12. Export center + validation.  
13. Model manager + checksums.  
14. Installer + first-run provisioning.  
15. Perf pass + benchmark publication.  
16. V2 separation spike integration (conditional).

---

## 6. Critical technical decisions (locked for MVP)

| Decision | Choice |
|----------|--------|
| License | GPL-3.0-or-later portfolio OSS |
| Shell | Electron + React + Vite + Tailwind + WaveSurfer |
| App services | Electron main + SQLite + IPC (no Node HTTP) |
| Engine | Python 3.12 FastAPI sidecar, loopback + token |
| Media owner | Node FFmpeg |
| DSP | SciPy + Pedalboard |
| Speech denoise | DeepFilterNet3 via ONNX/CLI (not pip) |
| Heavy ML | PyTorch CUDA; small models ORT CPU |
| Packaging | uv first-run env (not PyInstaller) |
| Separation | Not in MVP; Demucs optional V2 with notice |

---

## 7. Explicit MVP scope freeze

**In:** Docs-complete architecture; analyzer; rule planner; DSP; gated DFN; Silero+tagger; preview A/B; remux export; model manager MVP set; installer.

**Out:** Cloud, generative BWE, Demucs default, multichannel, DAW plugins, mobile, ML routing.

---

## 8. Related documents

- [TESTING_STRATEGY.md](TESTING_STRATEGY.md)
- [TECHNICAL_RISKS.md](TECHNICAL_RISKS.md)
- [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md)

# Technical Risks — AudioRestorer AI

**Status:** Approved planning document  
**Last reviewed:** 2026-11-23  
**Related:** [AI_MODEL_EVALUATION.md](AI_MODEL_EVALUATION.md), [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md), [DEVELOPMENT_ROADMAP.md](DEVELOPMENT_ROADMAP.md)

Likelihood / impact scale: **L**ow / **M**edium / **H**igh.

---

## 1. Risk register

| ID | Risk | L | I | Mitigation | Owner phase |
|----|------|---|---|------------|-------------|
| R1 | DeepFilterNet pip stack incompatible with Python 3.12 / numpy 2 | H | H | Integrate via ONNX Runtime CPU or official Windows CLI/LADSPA; never mainline pip package | P0–P3 |
| R2 | DeepFilterNet ONNX quality ≠ reference; Windows CLI I/O friction | M | H | Phase 0 A/B spike; pick one path; document latency compensation | P0 |
| R3 | Demucs / RoFormer **weight licenses** unclear or non-commercial | H | H | Do not bundle; optional download + notice; GPL app still OK for research weights as optional | P0, V2 |
| R4 | Concert separation adds little value (crowd in “other”) | M | M | Phase 0 listening spike; keep Demucs out of default path if no win | P0 |
| R5 | CUDA / PyTorch wheel drift vs driver 610 / sm_86 | M | H | Pin torch build; health check; CPU fallback; first-run device choice | P0, P8 |
| R6 | onnxruntime-gpu CUDA/cuDNN DLL hell on Windows | M | M | **Defer ORT-GPU**; use ORT CPU for small models; Torch for heavy | Arch lock |
| R7 | RTX 3070 8 GB OOM on stacked models | H | H | Sequential GPU queue; unload; segment limits; OOM→halve chunk→CPU | P3–P7 |
| R8 | Long-file RAM/disk exhaustion (float32 WAV stages) | M | H | RF64; streaming; stage retention policy; disk preflight | P1–P7 |
| R9 | A/V sync bugs from `-shortest`, latency, PTS offsets | M | H | Forbid `-shortest` as strategy; latency_samples contract; ffprobe+sample count verify | P6 |
| R10 | Chromium cannot play many containers/codecs | H | M | H.264 proxies + WAV/Opus A/B audio | P5–P6 |
| R11 | Electron security (IPC, path traversal, XSS via media) | M | H | contextIsolation, sandbox, zod IPC, allowlisted `media://`, no shell | P5 |
| R12 | Installer / runtime size (multi-GB torch) | H | M | First-run uv provisioning; CPU vs CUDA choice; don’t PyInstall torch | P8 |
| R13 | AudioSR dependency freeze (old numpy/librosa) | H | M | V3 isolated worker env only | V3 |
| R14 | Subjective quality / over-processing | H | H | Do-no-harm gates; presets; guards; honest UX; listening tests | P2–P7 |
| R15 | Speech enhancer damages music/ambience | H | H | VAD gating, hysteresis, attenuation limits, planner rules, tests | P3–P4 |
| R16 | Detector false positives (muffle/hiss on genre) | M | M | Content-conditional references; confidence bands; suggest vs enable | P2 |
| R17 | Solo scope creep | H | H | MVP freeze in PRD/roadmap; V2/V3 backlog only | All |
| R18 | FFmpeg GPL redistribution obligations | M | M | Ship source offer; document build; essentials pin + checksum | P8 |
| R19 | Pedalboard GPL → entire app GPL | L | L | Accepted (portfolio OSS GPL-3.0-or-later) | Decided |
| R20 | better-sqlite3 / native module Electron rebuild pain | M | M | electron-builder + electron-rebuild in packaging docs | P5, P8 |
| R21 | Model download supply-chain tampering | M | H | SHA-256 manifest; HTTPS; delete on mismatch | P3, P8 |
| R22 | Privacy leak via logs/crash dumps | M | M | No PCM in logs; path redaction setting; local-only crashes | P5–P8 |
| R23 | Smartphone pre-processed audio (AGC, gating) confuses detectors | M | M | Document limitation MVP; V2/V3 detectors | P2, V2 |
| R24 | Multichannel / exotic layouts mishandled | M | M | MVP warn + stereo policy; V2 full | P6 |
| R25 | Eval metrics misuse (PESQ on music) | M | M | Testing policy; harness category gates | P0, eval |
| R26 | Engine process zombie / port conflicts | M | M | Ephemeral port; supervisor kill tree; health checks | P5 |
| R27 | No system Python on dev machine today | H | L | Use uv + python-build-standalone (already planned) | P0 |
| R28 | PANNs weight license unclear on Zenodo | M | M | Confirm before bundle; else EfficientAT / inaSpeechSegmenter | P0 |
| R29 | Windows SmartScreen / unsigned installer | H | L | Document sideload; optional code signing later | P8 |
| R30 | Incomplete recovery after power loss mid-write | M | M | Atomic temp→rename writes; SQLite job states; checksum artifacts | P4–P6 |

---

## 2. Risk detail (highest priority)

### R1 / R2 — DeepFilterNet integration

**Evidence [Verified 2026-11-23]:** PyPI `deepfilternet` 0.5.6 (Aug 2023); wheels cp38–cp311; `numpy<2`; dual MIT/Apache code; Windows CLI asset ~25.7 MB exists.

**Impact:** Blocks MVP speech denoise if mishandled.

**Plan:** Phase 0 chooses ONNX vs CLI; adapter hides transport; attenuation limits + VAD gating mandatory.

### R3 — Weight licensing

**Evidence [Verified]:** Demucs author states weight license unclear / MUSDB research restrictions; NeMo SE CC-BY-NC-SA; AudioSR speech checkpoint unlicensed on HF.

**Plan:** License matrix in AI_MODEL_EVALUATION; optional downloads; never silent bundle of unclear weights.

### R7 / R8 — Resource limits

**Plan:** Single GPU worker; unload; chunk OLA; RF64; disk preflight formula `duration × sr × ch × 4 × retained_stages`.

### R9 — Sync

**Plan:** Node owns remux; verify sample counts; preserve `start_time`; no blind stream-copy assumptions for audio encode path.

### R14 / R15 — Quality ethics

**Plan:** UX recoverability labels; reconstruction labeling for generative tools; automated plan tests that speech FX never enable on music_dominant regions.

---

## 3. Feasibility summary

| Area | Feasibility | Notes |
|------|-------------|-------|
| Offline Windows desktop hybrid AI+DSP | **High** | Stack proven in industry patterns |
| MVP without separation / generative BWE | **High** | Strong DSP + gated DFN + analyzer |
| Shipping Demucs weights in installer | **Low** | License ambiguity |
| AudioSR in same env as modern torch | **Low** | Isolate in V3 |
| 8 GB VRAM full pipeline sequential | **Medium–High** | Requires discipline |
| Solo 8-week MVP | **Low** | Plan uses **26–32 weeks** |
| Solo 26–32 week MVP | **Medium–High** | Scope freeze required |

---

## 4. Critical technical decisions log

| # | Decision | Alternatives considered | Rationale | Status |
|---|----------|-------------------------|-----------|--------|
| D1 | GPL-3.0-or-later portfolio OSS | Commercial closed; personal-only | User choice; enables Pedalboard/FFmpeg GPL | **Locked** |
| D2 | Electron (not Tauri) | Tauri, Qt | Chromium media + Python sidecar still needed | **Locked** |
| D3 | App services in Electron main (no Node HTTP) | Separate Nest/Express API | Fewer processes; SQLite colocated | **Locked** |
| D4 | Python FastAPI sidecar + token | stdio JSON-RPC only | Debuggable OpenAPI contracts | **Locked** |
| D5 | Node owns FFmpeg; Python audio-only | Python remux | Clean boundary; sync validation | **Locked** |
| D6 | Python 3.12 + uv first-run (not PyInstaller) | Conda, embedded PyInstaller | Modern libs; torch-friendly | **Locked** |
| D7 | ORT CPU for small models; Torch CUDA for heavy | ORT-GPU everything | Avoid Windows CUDA DLL issues | **Locked** |
| D8 | DeepFilterNet via ONNX/CLI not pip | deepfilternet wheel | Compatibility | **Locked** (path pick in P0) |
| D9 | Rule-based planner MVP | ML router first | Testable, transparent | **Locked** |
| D10 | Demucs not in MVP; optional V2 | Bundle Demucs | License + value spike | **Locked** |
| D11 | AudioSR V3 isolated + “reconstruction” UX | MVP BWE | Quality/license/env risk | **Locked** |
| D12 | Preview proxies for video | Force remux to H.264 always | Preserve originals; Chromium gaps | **Locked** |
| D13 | Timeline ~26–32 weeks solo FT | 8-week demo | Honest engineering | **Locked** |

---

## 5. Unverified items (track in Phase 0)

- [ ] DeepFilterNet3 ONNX parity vs CLI on Windows  
- [ ] Exact peak VRAM / RTF for MVP adapters on RTX 3070  
- [ ] Torch CUDA wheel sm_86 with driver 610.88  
- [ ] PANNs CNN14 Zenodo weight license text  
- [ ] EfficientAT vs PANNs accuracy on local fixtures  
- [ ] Whether Demucs remix helps concert corpus enough for V2  

---

## 6. Assumptions (non-blocking)

1. Users accept multi-GB first-run download for CUDA torch.  
2. English-only UI for MVP.  
3. Eval corpus can be gathered privately by the developer.  
4. FFmpeg essentials GPL build remains acceptable with source offer.  
5. Solo full-time availability sustained across phases.

---

## 7. Open questions (non-blocking; defaults applied)

| Question | Default assumption |
|----------|--------------------|
| Code signing certificate? | Unsigned MVP; document SmartScreen |
| Per-project vs global SQLite? | Global app DB + project artifact dirs |
| Copy originals into project? | Reference by path; optional copy setting |
| Default loudness? | −16 LUFS |

---

## 8. Related documents

- [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md)
- [AI_MODEL_EVALUATION.md](AI_MODEL_EVALUATION.md)
- [DEVELOPMENT_ROADMAP.md](DEVELOPMENT_ROADMAP.md)
- [TESTING_STRATEGY.md](TESTING_STRATEGY.md)
- [PRODUCT_REQUIREMENTS.md](PRODUCT_REQUIREMENTS.md)

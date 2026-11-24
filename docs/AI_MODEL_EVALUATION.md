# AI Model Evaluation — AudioRestorer AI

**Status:** Approved planning document  
**Research date:** 2026-11-23 (GitHub API, PyPI, Hugging Face Hub)  
**Related:** [AUDIO_PIPELINE.md](AUDIO_PIPELINE.md), [TECHNICAL_RISKS.md](TECHNICAL_RISKS.md)

Labels used throughout:

- **[Verified]** — checked via API or primary docs on research date.
- **[Unverified]** — requires Phase 0 measurement or manual license review.
- **[Assumption]** — planning assumption pending validation.

---

## 1. Evaluation criteria

For every model/candidate, document:

1. Purpose  
2. Input/output requirements  
3. Supported sample rates and channels  
4. GPU/VRAM requirements  
5. Approximate model size (if verifiable)  
6. Inference performance considerations  
7. Licensing (code **and** weights separately)  
8. Known limitations  
9. Integration complexity  
10. MVP / V2 / V3 placement  

Additional product constraints:

- Never apply speech enhancement blindly to music.
- Never assume source separation restores information that was never recorded.
- Distinguish **restoration** from **AI-generated reconstruction**.
- Evaluate artifacts, not only popularity.
- Check checkpoint licenses independently of source code licenses.

---

## 2. Recommended model sets

### MVP (minimal)

| Role | Choice | Runtime |
|------|--------|---------|
| Speech activity | Silero VAD | ONNX Runtime CPU |
| Speech denoise | DeepFilterNet3 | ONNX Runtime CPU **or** official Windows CLI |
| Content tagging | PANNs CNN14 **or** EfficientAT (Phase 0 pick) | ONNX/Torch CPU preferred |
| Speech quality proxy (guards) | DNSMOS (Microsoft DNS-Challenge) | CPU |
| Restoration body | Adaptive DSP (SciPy + Pedalboard) | CPU |

### V2

| Role | Choice | Notes |
|------|--------|-------|
| Music stem separation | HTDemucs (`htdemucs` / `htdemucs_ft`) | Optional download + license notice; Phase 0 concert spike gate |
| Dereverb | `nara_wpe` | Classical, MIT |
| Declip advanced | A-SPADE (or equivalent) | After Janssen MVP |
| Alt speech denoise | resemble-enhance | MIT weights; inactive since Dec 2023 |

### V3

| Role | Choice | Notes |
|------|--------|-------|
| Bandwidth extension | AudioSR (`audiosr_basic`) | Isolated env; UI label **AI reconstruction** |
| Separation alt | BS-RoFormer community checkpoints | Per-checkpoint license review |
| Routing | Trained treatment classifier | Needs labeled dataset |

### Excluded from shipping (eval-only allowed)

| Model | Reason |
|-------|--------|
| NVIDIA NeMo SE (`se_den_sb_16k_small`) | **CC-BY-NC-SA-4.0** [Verified] |
| GTCRN, MP-SENet (16 kHz class) | Bandwidth too limited for general 48 kHz product path |
| facebookresearch/denoiser | Archived [Verified] |

---

## 3. Per-model evaluations

### 3.1 Silero VAD

| # | Attribute | Detail |
|---|-----------|--------|
| 1 | Purpose | Frame/region speech activity for gating enhancement |
| 2 | I/O | Mono waveform → speech probabilities / timestamps |
| 3 | Rates / channels | Commonly 8/16 kHz; resample from 48 kHz; mono |
| 4 | GPU/VRAM | CPU sufficient; tiny |
| 5 | Size | **[Unverified]** typically few MB ONNX |
| 6 | Performance | Real-time factor ≪ 1 on CPU **[Assumption]** |
| 7 | Licensing | Code MIT; package `silero-vad` 6.3 active [Verified] |
| 8 | Limitations | Not a content classifier; music with vocals may trigger; needs hysteresis for gating |
| 9 | Integration | Low — ONNX adapter |
| 10 | Phase | **MVP** |

---

### 3.2 DeepFilterNet3

| # | Attribute | Detail |
|---|-----------|--------|
| 1 | Purpose | Full-band speech noise suppression |
| 2 | I/O | Noisy speech audio → enhanced speech |
| 3 | Rates / channels | Designed for **48 kHz** full-band; typically mono processing, stereo via dual-mono or mid/side policy |
| 4 | GPU/VRAM | CPU real-time class via Rust/ONNX path preferred |
| 5 | Size | Standalone Windows exe ~25.7 MB [Verified release asset]; ONNX size **[Unverified]** |
| 6 | Performance | Real-time capable on CPU **[Assumption]**; measure RTF in Phase 0 |
| 7 | Licensing | Code dual MIT/Apache-2.0 [Verified via LICENSE files]; PyPI `deepfilternet` 0.5.6 lists MIT |
| 8 | Limitations | **Speech-oriented** — damages music/ambience if applied globally; can introduce musical noise at high attenuation; pip package **stale** (Aug 2023), wheels only cp38–cp311, pins `numpy<2` — **incompatible** with Python 3.12 + modern stack [Verified] |
| 9 | Integration | **Medium–High** — do **not** use pip package in main env; use ONNX Runtime or `deep-filter-*-pc-windows-msvc.exe` / LADSPA |
| 10 | Phase | **MVP** (gated by VAD + attenuation limits) |

**Integration policy:** Prefer ONNX if Phase 0 proves parity; else wrap official Windows CLI with temp WAV I/O and documented latency compensation.

---

### 3.3 PANNs CNN14 / EfficientAT (tagger candidates)

| # | Attribute | Detail |
|---|-----------|--------|
| 1 | Purpose | Audio event / scene tags: speech, music, crowd, wind, etc. |
| 2 | I/O | Audio chunks → tag probabilities |
| 3 | Rates / channels | Often 32 kHz mono for PANNs; resample from 48 kHz |
| 4 | GPU/VRAM | CPU preferred for MVP timeline analysis |
| 5 | Size | CNN14 weights tens–hundreds of MB **[Unverified exact]** |
| 6 | Performance | 1 s hop streaming feasible **[Assumption]** |
| 7 | Licensing | `audioset_tagging_cnn` MIT code [Verified]; **weight license on Zenodo must be confirmed** **[Unverified]**; `panns-inference` 0.1.1 last upload Mar 2023 [Verified] |
| 8 | Limitations | Audioset ontology ≠ degradation ontology; wind/crowd tags are proxies; not a muffling detector |
| 9 | Integration | Medium — ONNX export preferred; fallback Torch |
| 10 | Phase | **MVP** (choose one after Phase 0 license + accuracy spike) |

**inaSpeechSegmenter** (MIT, active) is a backup for speech/music/noise segmentation if tagging proves weak [Verified].

---

### 3.4 DNSMOS (quality proxy)

| # | Attribute | Detail |
|---|-----------|--------|
| 1 | Purpose | Non-intrusive speech quality estimate for guards / eval |
| 2 | I/O | Speech audio → MOS-like scores |
| 3 | Rates / channels | Typically 16 kHz mono |
| 4 | GPU/VRAM | CPU |
| 5 | Size | Small ONNX **[Unverified exact]** |
| 6 | Performance | Fast enough for segment sampling |
| 7 | Licensing | microsoft/DNS-Challenge **CC-BY-4.0** [Verified] |
| 8 | Limitations | **Speech-only** — never use as music quality metric |
| 9 | Integration | Low–Medium |
| 10 | Phase | **MVP** (guards + eval harness) |

---

### 3.5 HTDemucs (Demucs)

| # | Attribute | Detail |
|---|-----------|--------|
| 1 | Purpose | Music source separation (drums/bass/other/vocals) for optional rebalancing |
| 2 | I/O | Mixture → stems; remix with gains |
| 3 | Rates / channels | 44.1 kHz stereo typical for MUSDB-trained models |
| 4 | GPU/VRAM | ~3 GB min; ~7 GB default; HT segment max **7.8 s** [Verified README]; fits RTX 3070 with `--segment` tuning |
| 5 | Size | Hundreds of MB per checkpoint **[Unverified exact]** |
| 6 | Performance | GPU preferred; CPU ~1.5× duration [Verified README]; `htdemucs_ft` ~4× slower |
| 7 | Licensing | Code MIT (`adefossez/demucs`, PyPI 4.1.0) [Verified]; **weights license unclear** — MUSDB research restrictions; 6-stem “likely CC-NC” per author [Verified README]. **Never bundle.** Optional user download + notice. |
| 8 | Limitations | Does **not** restore missing mics; concert crowd often in “other”; can smear transients; Meta `facebookresearch/demucs` **archived** — use `adefossez/demucs` [Verified] |
| 9 | Integration | Medium — Torch adapter + VRAM manager; optional install |
| 10 | Phase | **V2**, gated by Phase 0 concert spike |

---

### 3.6 BS-RoFormer

| # | Attribute | Detail |
|---|-----------|--------|
| 1 | Purpose | Higher-quality separation alternative |
| 2 | I/O | Mixture → stems |
| 3 | Rates / channels | Checkpoint-dependent (often 44.1 kHz stereo) |
| 4 | GPU/VRAM | Often **higher** than Demucs; may stress 8 GB **[Unverified]** — measure |
| 5 | Size | Checkpoint-dependent; often large |
| 6 | Performance | Slower / heavier than HTDemucs typically **[Assumption]** |
| 7 | Licensing | Code MIT (`lucidrains/BS-RoFormer`, ZFTurbo training repo) [Verified]; **community weights: training data/licenses often undocumented** — per-checkpoint review required |
| 8 | Limitations | Same separation epistemology limits; packaging complexity via `audio-separator` (MIT, active 0.48.0) [Verified] |
| 9 | Integration | High |
| 10 | Phase | **V3** (after license-cleared checkpoint) |

---

### 3.7 AudioSR

| # | Attribute | Detail |
|---|-----------|--------|
| 1 | Purpose | Generative bandwidth extension / “super resolution” to ~48 kHz |
| 2 | I/O | Band-limited audio → extended audio |
| 3 | Rates / channels | Any → 48 kHz (per project claims); mono/stereo handling **[Unverified]** |
| 4 | GPU/VRAM | Diffusion-class; likely several GB **[Unverified]** |
| 5 | Size | Significant; HF `haoheliu/audiosr_basic` [Verified exists] |
| 6 | Performance | Slow vs real-time; chunk carefully |
| 7 | Licensing | Code MIT; `audiosr_basic` weights **Apache-2.0** [Verified HF]; `audiosr_speech` **no license tag** [Verified] — do not ship speech checkpoint without clarity. PyPI `audiosr` 0.0.7 (Feb 2024) pins ancient numpy/librosa/transformers [Verified] |
| 8 | Limitations | **Reconstruction, not restoration** — invents HF detail; artifacts on music; env isolation mandatory |
| 9 | Integration | **Very High** — isolated worker env |
| 10 | Phase | **V3**, UI-labeled AI reconstruction |

---

### 3.8 resemble-enhance

| # | Attribute | Detail |
|---|-----------|--------|
| 1 | Purpose | Speech denoise / enhance alternative |
| 2 | I/O | Noisy speech → enhanced |
| 3 | Rates / channels | Speech rates; mono typical |
| 4 | GPU/VRAM | Torch; measure on 8 GB **[Unverified]** |
| 5 | Size | HF `ResembleAI/resemble-enhance` [Verified] |
| 6 | Performance | Heavier than DeepFilterNet **[Assumption]** |
| 7 | Licensing | MIT weights tag [Verified HF]; repo inactive since Dec 2023 / Dec 2024 pushes [Verified] |
| 8 | Limitations | Maintenance risk; speech-only |
| 9 | Integration | Medium |
| 10 | Phase | **V2** optional adapter |

---

### 3.9 Classical / DSP-adjacent libraries (not “models” but evaluated)

| Package | License | Role | Phase | Notes |
|---------|---------|------|-------|-------|
| Pedalboard 0.9.26 | **GPL-3.0** [Verified] | Dynamics, limiter, some FX | MVP | OK under project GPL |
| SciPy / NumPy | BSD-style [Verified] | Filters, STFT, SOS | MVP | |
| Librosa 1.0.1 | ISC [Verified] | Features | MVP | Needs Python ≥3.12 |
| soundfile 0.14.0 | BSD-3 [Verified] | WAV/RF64 I/O | MVP | |
| pyloudnorm 0.2.0 | MIT [Verified] | Loudness | MVP | Cross-check with FFmpeg ebur128 |
| noisereduce 3.0.3 | MIT [Verified] | Spectral gate baseline | MVP optional | Prefer in-house gate with bounds |
| nara_wpe | MIT [Verified] | Dereverb | V2 | |
| Matchering | GPL-3.0 [Verified] | Reference mastering | **Out** | Not needed |

---

### 3.10 Janssen / A-SPADE declipping

| # | Attribute | Detail |
|---|-----------|--------|
| 1 | Purpose | Recover clipped samples |
| 2 | I/O | Clipped PCM → declipped PCM |
| 3 | Rates / channels | Rate-agnostic; per-channel |
| 4 | GPU/VRAM | CPU |
| 5 | Size | Algorithmic (no large weights) |
| 6 | Performance | Cost grows with clipped fraction |
| 7 | Licensing | Implement from literature / MIT sources; verify before copy |
| 8 | Limitations | Cannot invent lost headroom beyond model assumptions; smartphone soft-clip harder |
| 9 | Integration | Medium |
| 10 | Phase | Janssen-style **MVP**; A-SPADE **V2** |

---

## 4. License matrix (shipping posture)

| Component | Code | Weights | Bundle in installer? | User download? |
|-----------|------|---------|----------------------|----------------|
| App (AudioRestorer AI) | GPL-3.0-or-later | n/a | Yes | n/a |
| FFmpeg essentials GPL | GPL | n/a | Yes + source offer | n/a |
| Pedalboard | GPL-3.0 | n/a | Yes (via engine) | n/a |
| Silero VAD | MIT | MIT **[Assumption confirm]** | Yes | Optional update |
| DeepFilterNet | MIT/Apache | Treat as OSS; confirm checkpoint notice | Yes (ORT/CLI) | Yes |
| PANNs / EfficientAT | MIT code | **Confirm Zenodo** | Only if cleared | Yes |
| DNSMOS | CC-BY-4.0 | CC-BY-4.0 | Yes (attribution) | Yes |
| HTDemucs | MIT | **Unclear / research** | **No** | Optional + notice |
| BS-RoFormer ckpts | MIT code | Often unclear | **No** | Only if cleared |
| AudioSR basic | MIT | Apache-2.0 | No (V3 optional) | Yes |
| NeMo SE | Apache code | **CC-BY-NC-SA** | **No** | Eval only |

---

## 5. Artifact and epistemology guidance

| Technique | Class | User-facing label |
|-----------|-------|-------------------|
| EQ restoring obstructed-mic HF tilt (SNR-limited) | Restoration | “Spectral restoration” |
| Notch hum removal | Restoration | “Hum reduction” |
| DeepFilterNet on speech regions | Enhancement / restoration | “Speech noise reduction” — warn ambience impact |
| Declipping | Partial restoration | “Clipping repair (partial)” |
| Source separation remix | Rebalancing, not creation | “Stem rebalance” — does not add missing instruments |
| AudioSR / generative BWE | **Reconstruction** | “AI bandwidth reconstruction” |

---

## 6. Phase 0 validation checklist

1. DeepFilterNet3 ONNX vs Windows CLI: PESQ/STOI/DNSMOS + listening on fixtures.  
2. Torch CUDA wheel installs and runs Demucs segment on RTX 3070 8 GB.  
3. Tagger accuracy on speech/music/mixed fixtures; finalize PANNs vs EfficientAT vs inaSpeechSegmenter.  
4. PANNs weight license text captured.  
5. Concert spike: Demucs remix vs DSP-only — if no clear win, keep Demucs out of default V2 path.  
6. Record RTF and peak VRAM for each MVP adapter.  

---

## 7. Related documents

- [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md)
- [AUDIO_PIPELINE.md](AUDIO_PIPELINE.md)
- [TESTING_STRATEGY.md](TESTING_STRATEGY.md)
- [TECHNICAL_RISKS.md](TECHNICAL_RISKS.md)

# Testing Strategy — AudioRestorer AI

**Status:** Approved planning document  
**Related:** [AUDIO_PIPELINE.md](AUDIO_PIPELINE.md), [DEVELOPMENT_ROADMAP.md](DEVELOPMENT_ROADMAP.md), [PRODUCT_REQUIREMENTS.md](PRODUCT_REQUIREMENTS.md)

---

## 1. Goals

1. Prove **technical correctness** (sync, length, loudness, no NaNs).  
2. Prove **audio quality** with category-appropriate metrics and listening tests.  
3. Prevent regressions via golden fixtures and CI-friendly unit tests.  
4. Never misuse **speech metrics as music quality**.  
5. Compare **Original / DSP-only / AI-only / Hybrid** fairly.

---

## 2. Test layers

| Layer | Tools | Scope |
|-------|-------|-------|
| Python unit | pytest | DSP transfer functions, planners, detectors on synthetics |
| Python property | hypothesis / custom | Length preserve, finite samples, near-identity on clean |
| Python integration | pytest | Engine API analyze/plan/render on fixtures |
| TypeScript unit | Vitest | zod schemas, path allowlists, job state machine |
| Desktop e2e | Playwright for Electron | Import → analyze → preview → export smoke |
| Media matrix | scripts + ffprobe | Containers, VFR, offsets, multi-stream, corrupt |
| Eval harness | `eval/` | Benchmarks A/B/C/D + reports |
| Manual listening | ABX / MUSHRA-style | Per category preference |

CI (when introduced): unit + planner + synthetic detector tests on CPU; GPU tests local-only on reference machine.

---

## 3. Evaluation corpus

Media is **not** stored in git. Use manifests with local paths + hashes.

### 3.1 Categories

| Category | Examples | Count target (MVP) |
|----------|----------|--------------------|
| Synthetic degradations | Clean + injected hum/hiss/clip/muffle/wind/noise | ≥ 30 clips |
| Smartphone | Voice notes, outdoor speech, phone concert | ≥ 10 |
| Concert / live music | Audience recordings, PA bleed | ≥ 8 |
| Speech / dialogue | Interviews, podcasts, rooms | ≥ 10 |
| Mixed | Vlog with music beds, event videos | ≥ 8 |
| Clean controls | Studio speech/music lightly processed | ≥ 6 |

### 3.2 Synthetic degradation generator

Controllable operators:

- Additive noise (white/pink) at SNR grid.  
- Hum (50/60 Hz + harmonics).  
- Hiss (HF shaped).  
- Clipping (hard + soft tanh).  
- Muffling (lowpass + shelf).  
- Wind (modulated LF noise bursts).  
- Narrowband distortion.  
- Stereo imbalance / polarity invert.  
- Loudness offsets.

Each synthetic item stores **ground-truth issue labels** and optional **clean reference**.

### 3.3 Real recordings

- Prefer self-recorded or clearly licensed assets.  
- Document device, app processing (if known), and ethics notes.  
- No scraped copyrighted commercial tracks in public repos.

---

## 4. Metrics (by applicability)

### 4.1 Universal / engineering

| Metric | Use |
|--------|-----|
| Sample count equality | Hard gate |
| NaN/Inf detection | Hard gate |
| LUFS integrated / LRA | Loudness targets |
| True peak (dBTP) | Limiter compliance |
| Clipping ratio | Before/after |
| Spectral distance (e.g. log-mel L2) | Guard / regression |
| RTF, peak RSS, peak VRAM | Performance |

### 4.2 Speech-only

| Metric | Use |
|--------|-----|
| PESQ | Intrusive quality (when ref exists) |
| STOI | Intelligibility |
| DNSMOS | Non-intrusive proxy / guards |

**Do not** report PESQ/STOI as primary scores for music or mixed music-dominant regions.

### 4.3 Reference-based (synthetic)

| Metric | Use |
|--------|-----|
| SI-SDR / SI-SIR | Enhancement vs known clean |
| Bandwise SNR | Muffling/EQ recovery |

### 4.4 Music / general perceptual

| Method | Use |
|--------|-----|
| Blind ABX | Detectability of processing on clean |
| Preference vs original | Hybrid acceptance |
| Artifact checklists | Musical noise, pumping, dulling, transient smear |
| Residual listening | Sanity of what was removed |

### 4.5 Artifact detectors (automated heuristics)

- Musical noise / tonal remnants after denoise.  
- Pumping (envelope correlation with noise estimate).  
- Excess HF (harshness) after treble recovery.  
- Bass loss after wind HPF on music.

---

## 5. Benchmark design: A / B / C / D

For each fixture (where applicable):

| Arm | Description |
|-----|-------------|
| **A. Original** | Unprocessed extracted audio |
| **B. DSP only** | Planner stages without neural denoise/separation |
| **C. AI only** | Neural stages only (e.g. DFN) with minimal DSP |
| **D. Hybrid** | Full recommended plan (product path) |

### Protocol

1. Fix random seeds and model versions in the report.  
2. Loudness-match arms for listening (document match method).  
3. Compute applicable objective metrics per category.  
4. Run listening: at least 5 listeners when possible; solo developer uses ABX + structured self-blind notes as interim.  
5. Store outputs under `eval/output/` (gitignored) with JSON summary.

### Reporting template

- Fixture id, category, versions.  
- Table of metrics per arm.  
- Listener preference counts.  
- Failures / guard skips.  
- RTF and VRAM.

---

## 6. Detector acceptance (synthetic)

Draft targets to calibrate in Phase 0–2:

| Detector | TPR | Max FPR on clean |
|----------|-----|------------------|
| Hum | ≥ 0.9 | ≤ 0.1 |
| Hard clip (≥1% samples) | ≥ 0.95 | ≤ 0.05 |
| Hiss (SNR-defined) | ≥ 0.85 | ≤ 0.15 |
| Muffle (known LPF) | ≥ 0.8 | ≤ 0.2 |
| Wind (synthetic) | ≥ 0.75 | ≤ 0.2 |

Content labeling: speech vs music dominant accuracy ≥ 0.85 on tagged synthetic mix timelines.

---

## 7. MVP acceptance criteria

### Hard gates (must pass)

1. Output sample count equals input for restore and export paths.  
2. Zero A/V drift on stream-copy remux verification suite (PTS/start_time cases included).  
3. True peak ≤ target ceiling + 0.1 dB when limiter enabled.  
4. Loudness within ±0.5 LU of target when normalization enabled.  
5. Clean control SI-SDR ≥ 30 dB for mild Natural preset (do-no-harm).  
6. No NaNs/Infs in outputs.  
7. 2-hour stereo fixture completes on RTX 3070 8 GB / 32 GB RAM without OOM.  
8. Cooperative cancellation ≤ 2 s.  
9. Hum synthetic: ≥ 25 dB suppression at f0 with &lt; 0.5 dB change outside notches (± measurement tolerance).

### Quality gates (calibrate numerically in Phase 0; directional for planning)

10. Noisy speech: PESQ and STOI improve vs original for Hybrid and AI-only.  
11. DNSMOS improves on speech denoise fixtures without collapsing ambience metrics beyond preset policy.  
12. Hybrid preferred over Original in ≥ **70%** of blind trials **per category** (speech, music, mixed, smartphone) once listening panel exists; interim solo ABX documented.  
13. Music-dominant fixtures: speech enhancer **not** applied globally (automation test on plan).  
14. Planner unit tests cover conflict rules (HF boost vs hiss, etc.).

### Product gates

15. Fresh install provisioning path succeeds offline after caches filled.  
16. Model checksum mismatch is surfaced and file deleted.  
17. Electron security smoke: path escape rejected; nodeIntegration false.

---

## 8. Media matrix tests

| Case | Expect |
|------|--------|
| MP4 H.264 + AAC | Remux OK |
| MOV | Remux OK |
| MKV Opus/FLAC | Remux OK |
| AVI | Warn / suggest MKV |
| VFR video | Video stream-copy preserved |
| Dual audio streams | Selected replaced; other copied |
| Audio start delay | Offset preserved |
| Mono / stereo | Channel policy documented |
| RF64 long WAV | Streaming path |
| Truncated file | Fail or warn, no silent shorten |
| Interrupted restore | Resume |

---

## 9. Regression policy

- Golden WAV hashes are **not** brittle bit-exact across platforms; use metric tolerances + optional waveform SNR floors.  
- Pin model versions in eval reports.  
- Any change to planner defaults requires re-running category smoke set.  
- DSP filter coefficients: compare frequency response to analytic target within dB epsilon.

---

## 10. Performance benchmark methodology

On reference hardware (i7-14700F, RTX 3070 8 GB, 32 GB RAM, NVMe, Win11):

1. Warm-up run discarded.  
2. Measure wall time for analyze, preview 20 s, full restore.  
3. RTF = wall / media_duration.  
4. Record peak VRAM (`nvidia-smi` sampling) and peak working set.  
5. Report **ranges**, never single marketing numbers without methodology.

Publish results in eval reports after Phase 7; do not promise unverified speeds in UI copy.

---

## 11. Related documents

- [PRODUCT_REQUIREMENTS.md](PRODUCT_REQUIREMENTS.md)
- [AUDIO_PIPELINE.md](AUDIO_PIPELINE.md)
- [AI_MODEL_EVALUATION.md](AI_MODEL_EVALUATION.md)
- [DEVELOPMENT_ROADMAP.md](DEVELOPMENT_ROADMAP.md)

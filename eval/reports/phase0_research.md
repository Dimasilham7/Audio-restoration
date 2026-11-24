# Phase 0 research report

Generated: 2026-11-24 19:57:02

| Item | Status | Detail |
|------|--------|--------|
| `dfn_cli_present` | EVIDENCE | D:\portofolio\audio-restoration\.models\deepfilternet\deep-filter.exe |
| `dfn_onnx_parity` | OPEN | OPEN: MVP uses official CLI; ONNX parity vs CLI not measured (deferred) |
| `torch_cuda` | OPEN | torch not installed: No module named 'torch' |
| `sm_86_runtime` | OPEN | skipped |
| `nvidia_smi` | EVIDENCE | NVIDIA GeForce RTX 3070, 8192 MiB, 610.88 |
| `panns_license` | OPEN | OPEN: PANNs CNN14 on Zenodo: verify license text before bundling; default remains unbundled / EfficientAT alternative. |
| `efficientat_vs_panns` | OPEN | OPEN: no local accuracy bake-off yet; keep heuristic content labels in MVP |
| `demucs_concert_value` | OPEN | OPEN: V2 optional; listening spike not run (adapter scaffolded, disabled by default) |

## Decision

- Keep DeepFilterNet **CLI** for MVP (pip wheel rejected).
- Do not bundle Demucs/AudioSR/PANNs weights until license + value gates pass.
- Torch CUDA remains optional; engine MVP path is CPU DSP + DFN CLI.

# Windows Sandbox attempt

Generated: 2026-11-24 19:57:02

- Feature query failed (likely needs elevation): The requested operation requires elevation.

- Setup exists: True
- Portable exists: True
- Wrote WSB: C:\Users\acer\AppData\Local\Temp\AudioRestorerSandbox.wsb
- WindowsSandbox.exe: **not available** (enable Windows Sandbox as admin, or use portable smoke)
- Fallback: ran/use `packaging/portable-smoke.ps1` for offline bundled-engine proof

## Checklist
# Windows Sandbox clean-install checklist

Use after `pnpm release:win`.

1. Start **Windows Sandbox** (optional feature in Windows 11 Pro/Enterprise).
2. Copy `AudioRestorer-AI-*-Setup.exe` into the sandbox desktop.
3. Confirm sandbox has **no** Python, uv, or FFmpeg on PATH.
4. Run the installer; accept SmartScreen **More info â†’ Run anyway** if shown (unsigned portfolio build).
5. Launch **AudioRestorer AI** from Start Menu.
6. Expect window within ~2 s; status text moves to â€œEngine readyâ€.
7. **Add folder** with a few MP4/WAV samples (copy from host).
8. Click **Process all**; watch per-row progress bars.
9. Select a completed row â†’ **B Restored** A/B audio.
10. **Show output** and open the remuxed MP4 in the sandbox Movies & TV app.
11. Repeat with the **portable** `.exe` from a USB-style folder path with spaces.

Pass if all steps succeed offline without installing Python/FFmpeg.


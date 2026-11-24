# Windows Sandbox clean-install checklist

Use after `pnpm release:win`.

1. Start **Windows Sandbox** (optional feature in Windows 11 Pro/Enterprise).
2. Copy `AudioRestorer-AI-*-Setup.exe` into the sandbox desktop.
3. Confirm sandbox has **no** Python, uv, or FFmpeg on PATH.
4. Run the installer; accept SmartScreen **More info → Run anyway** if shown (unsigned portfolio build).
5. Launch **AudioRestorer AI** from Start Menu.
6. Expect window within ~2 s; status text moves to “Engine ready”.
7. **Add folder** with a few MP4/WAV samples (copy from host).
8. Click **Process all**; watch per-row progress bars.
9. Select a completed row → **B Restored** A/B audio.
10. **Show output** and open the remuxed MP4 in the sandbox Movies & TV app.
11. Repeat with the **portable** `.exe` from a USB-style folder path with spaces.

Pass if all steps succeed offline without installing Python/FFmpeg.

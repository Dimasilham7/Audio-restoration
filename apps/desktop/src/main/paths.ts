import { app } from "electron";
import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const moduleDir = dirname(fileURLToPath(import.meta.url));

export function isPackaged(): boolean {
  return app.isPackaged;
}

export function repoRoot(): string {
  let dir = resolve(moduleDir);
  for (let i = 0; i < 8; i++) {
    if (existsSync(join(dir, "engine", "pyproject.toml"))) return dir;
    const parent = resolve(dir, "..");
    if (parent === dir) break;
    dir = parent;
  }
  return resolve(moduleDir, "../../../..");
}

export function resourcesRoot(): string {
  if (isPackaged()) {
    return process.resourcesPath;
  }
  // Dev: prefer apps/desktop/resources if present, else packaging/bin + .models
  const desktopRes = join(repoRoot(), "apps", "desktop", "resources");
  if (existsSync(desktopRes)) return desktopRes;
  return join(repoRoot(), "packaging");
}

export function binDir(): string {
  if (isPackaged()) {
    return join(process.resourcesPath, "bin");
  }
  const candidates = [
    join(repoRoot(), "apps", "desktop", "resources", "bin"),
    join(repoRoot(), "packaging", "bin"),
  ];
  for (const c of candidates) {
    if (existsSync(c)) return c;
  }
  // Fall back to known local ffmpeg install for developers
  const local = "D:\\tools\\ffmpeg\\ffmpeg-9.0.1-essentials_build\\bin";
  if (existsSync(local)) return local;
  return candidates[0];
}

export function engineDir(): string {
  return join(repoRoot(), "engine");
}

export function frozenEngineExe(): string | null {
  const candidates = [
    join(resourcesRoot(), "engine", "audiorestorer-engine.exe"),
    join(process.resourcesPath ?? "", "engine", "audiorestorer-engine.exe"),
  ];
  for (const c of candidates) {
    if (c && existsSync(c)) return c;
  }
  return null;
}

export function deepFilterExe(): string | null {
  const candidates = [
    join(binDir(), "deep-filter.exe"),
    join(repoRoot(), ".models", "deepfilternet", "deep-filter.exe"),
  ];
  for (const c of candidates) {
    if (existsSync(c)) return c;
  }
  return null;
}

export function defaultOutputDir(): string {
  return join(app.getPath("videos"), "AudioRestorer");
}

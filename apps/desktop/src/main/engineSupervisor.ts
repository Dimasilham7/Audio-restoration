import { ChildProcessWithoutNullStreams, spawn } from "node:child_process";
import { createInterface } from "node:readline";
import { randomBytes } from "node:crypto";
import { existsSync } from "node:fs";
import { binDir, deepFilterExe, engineDir, frozenEngineExe, isPackaged } from "./paths";

export type EngineInfo = {
  port: number;
  token: string;
  baseUrl: string;
};

type SupervisorState = {
  child: ChildProcessWithoutNullStreams | null;
  info: EngineInfo | null;
  starting: Promise<EngineInfo> | null;
};

const state: SupervisorState = {
  child: null,
  info: null,
  starting: null,
};

function resolveUv(): string {
  if (process.platform !== "win32") return "uv";
  const candidates = [
    process.env.UV_PATH,
    "uv.exe",
    "uv",
    ...(process.env.USERPROFILE
      ? [
          `${process.env.USERPROFILE}\\.local\\bin\\uv.exe`,
          `${process.env.USERPROFILE}\\.cargo\\bin\\uv.exe`,
          `${process.env.LOCALAPPDATA}\\Programs\\uv\\uv.exe`,
        ]
      : []),
  ].filter(Boolean) as string[];
  for (const c of candidates) {
    if (c === "uv" || c === "uv.exe") continue;
    if (existsSync(c)) return c;
  }
  return "uv.exe";
}

function buildEnv(token: string): NodeJS.ProcessEnv {
  const bin = binDir();
  const dfn = deepFilterExe();
  const pathSep = process.platform === "win32" ? ";" : ":";
  return {
    ...process.env,
    AUDIORESTORER_TOKEN: token,
    AUDIORESTORER_BIN_DIR: bin,
    PYTHONUTF8: "1",
    PYTHONIOENCODING: "utf-8",
    PYTHONUNBUFFERED: "1",
    ...(dfn ? { AUDIORESTORER_DFN_EXE: dfn } : {}),
    PATH: `${bin}${pathSep}${process.env.PATH ?? ""}`,
  };
}

export async function ensureEngine(): Promise<EngineInfo> {
  if (state.info && state.child && !state.child.killed) {
    return state.info;
  }
  if (state.starting) return state.starting;
  state.starting = startEngine().finally(() => {
    state.starting = null;
  });
  return state.starting;
}

async function startEngine(): Promise<EngineInfo> {
  const token = randomBytes(24).toString("hex");
  const frozen = frozenEngineExe();
  let child: ChildProcessWithoutNullStreams;

  if (frozen && isPackaged()) {
    child = spawn(frozen, ["serve", "--host", "127.0.0.1", "--port", "0", "--token", token], {
      env: buildEnv(token),
      shell: false,
      windowsHide: true,
    });
  } else {
    const uv = resolveUv();
    child = spawn(
      uv,
      ["run", "audiorestorer-engine", "serve", "--host", "127.0.0.1", "--port", "0", "--token", token],
      {
        cwd: engineDir(),
        env: buildEnv(token),
        shell: false,
        windowsHide: true,
      },
    );
  }

  state.child = child;
  let stderrBuf = "";
  child.stderr.on("data", (d) => {
    stderrBuf += String(d);
    if (stderrBuf.length > 8000) stderrBuf = stderrBuf.slice(-8000);
  });

  try {
    const port = await waitForReady(child, 45_000);
    const info: EngineInfo = {
      port,
      token,
      baseUrl: `http://127.0.0.1:${port}`,
    };
    state.info = info;

    child.on("exit", () => {
      if (state.child === child) {
        state.child = null;
        state.info = null;
      }
    });

    await waitHealth(info, 15_000);
    return info;
  } catch (err) {
    const detail = stderrBuf.trim().slice(-1500);
    const msg = err instanceof Error ? err.message : String(err);
    stopEngine();
    throw new Error(detail ? `${msg}\n${detail}` : msg);
  }
}

function waitForReady(child: ChildProcessWithoutNullStreams, timeoutMs: number): Promise<number> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      cleanup();
      reject(new Error("Engine READY timeout"));
    }, timeoutMs);

    const rl = createInterface({ input: child.stdout });
    const onLine = (line: string) => {
      const m = /READY port=(\d+)/.exec(line);
      if (m) {
        cleanup();
        resolve(Number(m[1]));
      }
    };
    const onErr = (err: Error) => {
      cleanup();
      reject(err);
    };
    const onExit = (code: number | null) => {
      cleanup();
      reject(new Error(`Engine exited before READY (code=${code})`));
    };

    function cleanup() {
      clearTimeout(timer);
      rl.off("line", onLine);
      child.off("error", onErr);
      child.off("exit", onExit);
      rl.close();
    }

    rl.on("line", onLine);
    child.on("error", onErr);
    child.on("exit", onExit);
  });
}

async function waitHealth(info: EngineInfo, timeoutMs: number): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(`${info.baseUrl}/v1/health`);
      if (res.ok) return;
    } catch {
      // retry
    }
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error("Engine health check timeout");
}

export async function engineFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const info = await ensureEngine();
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${info.token}`);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return fetch(`${info.baseUrl}${path}`, { ...init, headers });
}

export function stopEngine(): void {
  if (state.child && !state.child.killed) {
    if (process.platform === "win32" && state.child.pid) {
      spawn("taskkill", ["/pid", String(state.child.pid), "/T", "/F"], {
        shell: false,
        windowsHide: true,
      });
    } else {
      state.child.kill("SIGTERM");
    }
  }
  state.child = null;
  state.info = null;
}

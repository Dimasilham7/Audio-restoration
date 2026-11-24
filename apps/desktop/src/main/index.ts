import { app, BrowserWindow, dialog, ipcMain, protocol, shell } from "electron";
import { existsSync, mkdirSync } from "node:fs";
import { dirname, extname, join, normalize, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { cancelJob, createJob, getJob, watchJob } from "./jobs";
import { ensureEngine, stopEngine } from "./engineSupervisor";
import { defaultOutputDir, engineDir, repoRoot } from "./paths";

protocol.registerSchemesAsPrivileged([
  {
    scheme: "media",
    privileges: { standard: true, secure: true, supportFetchAPI: true, stream: true, bypassCSP: true },
  },
]);

let mainWindow: BrowserWindow | null = null;
const allowedMediaRoots: string[] = [];

function addMediaRoot(p: string) {
  const root = normalize(resolve(p));
  if (!allowedMediaRoots.includes(root)) allowedMediaRoots.push(root);
}

function isUnderAllowed(filePath: string): boolean {
  const target = normalize(resolve(filePath)).toLowerCase();
  return allowedMediaRoots.some((root) => target.startsWith(normalize(root).toLowerCase() + "\\") || target === normalize(root).toLowerCase());
}

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1320,
    height: 880,
    minWidth: 960,
    minHeight: 640,
    title: "AudioRestorer AI",
    show: false,
    backgroundColor: "#0e1210",
    webPreferences: {
      preload: join(__dirname, "../preload/index.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  mainWindow.once("ready-to-show", () => mainWindow?.show());

  if (process.env.ELECTRON_RENDERER_URL) {
    void mainWindow.loadURL(process.env.ELECTRON_RENDERER_URL);
  } else {
    void mainWindow.loadFile(join(__dirname, "../renderer/index.html"));
  }
}

app.whenReady().then(() => {
  protocol.handle("media", (request) => {
    try {
      const url = new URL(request.url);
      // media://local/C:/path/to/file.wav  OR media://local/?path=...
      let filePath = decodeURIComponent(url.pathname.replace(/^\/+/, ""));
      if (url.searchParams.get("path")) {
        filePath = decodeURIComponent(url.searchParams.get("path")!);
      }
      // Windows: media://local/D:/foo -> pathname may be /D:/foo
      if (/^[A-Za-z]:\//.test(filePath) === false && /^[A-Za-z]%3A/i.test(filePath)) {
        filePath = decodeURIComponent(filePath);
      }
      if (filePath.startsWith("/") && /^\/[A-Za-z]:/.test(filePath)) {
        filePath = filePath.slice(1);
      }
      filePath = normalize(filePath);
      if (!isUnderAllowed(filePath) || !existsSync(filePath)) {
        return new Response("Forbidden", { status: 403 });
      }
      return netFetchFile(filePath);
    } catch {
      return new Response("Bad Request", { status: 400 });
    }
  });

  addMediaRoot(defaultOutputDir());
  addMediaRoot(join(repoRoot(), "eval"));

  // Warm engine in background — do not block window
  void ensureEngine().catch((err) => console.error("engine start failed", err));

  ipcMain.handle("dialog:openMedia", async () => {
    const result = await dialog.showOpenDialog({
      title: "Import media",
      properties: ["openFile", "multiSelections"],
      filters: [
        {
          name: "Media",
          extensions: ["mp4", "mov", "mkv", "avi", "wav", "mp3", "m4a", "flac", "aac"],
        },
      ],
    });
    if (result.canceled) return [];
    for (const p of result.filePaths) addMediaRoot(dirname(p));
    return result.filePaths;
  });

  ipcMain.handle("dialog:openFolder", async () => {
    const result = await dialog.showOpenDialog({
      title: "Import folder",
      properties: ["openDirectory"],
    });
    if (result.canceled || !result.filePaths[0]) return null;
    addMediaRoot(result.filePaths[0]);
    return result.filePaths[0];
  });

  ipcMain.handle("dialog:chooseOutput", async () => {
    const result = await dialog.showOpenDialog({
      title: "Output folder",
      properties: ["openDirectory", "createDirectory"],
    });
    if (result.canceled || !result.filePaths[0]) return null;
    addMediaRoot(result.filePaths[0]);
    return result.filePaths[0];
  });

  ipcMain.handle("fs:listMediaInFolder", async (_e, folder: string) => {
    const { readdirSync, statSync } = await import("node:fs");
    const exts = new Set([".mp4", ".mov", ".mkv", ".avi", ".wav", ".mp3", ".m4a", ".flac", ".aac"]);
    const root = normalize(folder);
    addMediaRoot(root);
    return readdirSync(root)
      .filter((n) => exts.has(extname(n).toLowerCase()))
      .map((n) => join(root, n))
      .filter((p) => statSync(p).isFile());
  });

  ipcMain.handle("jobs:create", async (_e, payload) => createJob(payload));
  ipcMain.handle("jobs:get", async (_e, id: string) => getJob(id));
  ipcMain.handle("jobs:cancel", async (_e, id: string) => cancelJob(id));
  ipcMain.handle("jobs:watch", async (_e, id: string) => {
    if (!mainWindow) throw new Error("No window");
    return watchJob(id, mainWindow);
  });

  ipcMain.handle("shell:showItem", async (_e, path: string) => {
    shell.showItemInFolder(path);
  });

  ipcMain.handle("app:info", async () => ({
    version: app.getVersion(),
    repoRoot: repoRoot(),
    engineDir: engineDir(),
    defaultOutputDir: defaultOutputDir(),
  }));

  ipcMain.handle("app:ensureOutputDir", async (_e, dir?: string) => {
    const out = dir || defaultOutputDir();
    mkdirSync(out, { recursive: true });
    addMediaRoot(out);
    return out;
  });

  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  stopEngine();
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  stopEngine();
});

async function netFetchFile(filePath: string): Promise<Response> {
  // Use Electron net.fetch for file://
  const { net } = await import("electron");
  return net.fetch(pathToFileURL(filePath).toString());
}

import { contextBridge, ipcRenderer } from "electron";

export type DesktopApi = {
  openMedia: () => Promise<string[]>;
  openFolder: () => Promise<string | null>;
  chooseOutput: () => Promise<string | null>;
  listMediaInFolder: (folder: string) => Promise<string[]>;
  createJob: (payload: {
    kind: "analyze" | "process";
    mediaPath: string;
    outputPath?: string;
    workDir?: string;
    settings?: Record<string, unknown>;
  }) => Promise<Record<string, unknown>>;
  getJob: (id: string) => Promise<Record<string, unknown>>;
  cancelJob: (id: string) => Promise<Record<string, unknown>>;
  watchJob: (id: string) => Promise<Record<string, unknown>>;
  onJobProgress: (cb: (data: Record<string, unknown>) => void) => () => void;
  showItem: (path: string) => Promise<void>;
  appInfo: () => Promise<{
    version: string;
    repoRoot: string;
    engineDir: string;
    defaultOutputDir: string;
  }>;
  ensureOutputDir: (dir?: string) => Promise<string>;
  toMediaUrl: (filePath: string) => string;
};

const api: DesktopApi = {
  openMedia: () => ipcRenderer.invoke("dialog:openMedia"),
  openFolder: () => ipcRenderer.invoke("dialog:openFolder"),
  chooseOutput: () => ipcRenderer.invoke("dialog:chooseOutput"),
  listMediaInFolder: (folder) => ipcRenderer.invoke("fs:listMediaInFolder", folder),
  createJob: (payload) => ipcRenderer.invoke("jobs:create", payload),
  getJob: (id) => ipcRenderer.invoke("jobs:get", id),
  cancelJob: (id) => ipcRenderer.invoke("jobs:cancel", id),
  watchJob: (id) => ipcRenderer.invoke("jobs:watch", id),
  onJobProgress: (cb) => {
    const listener = (_: unknown, data: Record<string, unknown>) => cb(data);
    ipcRenderer.on("job:progress", listener);
    return () => ipcRenderer.removeListener("job:progress", listener);
  },
  showItem: (path) => ipcRenderer.invoke("shell:showItem", path),
  appInfo: () => ipcRenderer.invoke("app:info"),
  ensureOutputDir: (dir) => ipcRenderer.invoke("app:ensureOutputDir", dir),
  toMediaUrl: (filePath) => `media://local/?path=${encodeURIComponent(filePath)}`,
};

contextBridge.exposeInMainWorld("audiorestorer", api);

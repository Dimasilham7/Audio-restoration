import type { BrowserWindow } from "electron";
import { engineFetch, ensureEngine } from "./engineSupervisor";

export type CreateJobPayload = {
  kind: "analyze" | "process";
  mediaPath: string;
  outputPath?: string;
  workDir?: string;
  settings?: Record<string, unknown>;
};

export async function createJob(payload: CreateJobPayload): Promise<Record<string, unknown>> {
  const body = {
    kind: payload.kind,
    media_path: payload.mediaPath,
    output_path: payload.outputPath,
    work_dir: payload.workDir,
    settings: payload.settings,
  };
  const res = await engineFetch("/v1/jobs", {
    method: "POST",
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `create job failed: ${res.status}`);
  }
  return (await res.json()) as Record<string, unknown>;
}

export async function getJob(jobId: string): Promise<Record<string, unknown>> {
  const res = await engineFetch(`/v1/jobs/${jobId}`);
  if (!res.ok) throw new Error(`get job failed: ${res.status}`);
  return (await res.json()) as Record<string, unknown>;
}

export async function cancelJob(jobId: string): Promise<Record<string, unknown>> {
  const res = await engineFetch(`/v1/jobs/${jobId}/cancel`, { method: "POST" });
  if (!res.ok) throw new Error(`cancel failed: ${res.status}`);
  return (await res.json()) as Record<string, unknown>;
}

/** Poll job status and push progress to renderer (SSE polyfill via polling for simplicity/reliability). */
export async function watchJob(
  jobId: string,
  win: BrowserWindow,
  intervalMs = 150,
): Promise<Record<string, unknown>> {
  await ensureEngine();
  // Prefer SSE when available
  try {
    return await watchJobSse(jobId, win);
  } catch {
    return watchJobPoll(jobId, win, intervalMs);
  }
}

async function watchJobSse(jobId: string, win: BrowserWindow): Promise<Record<string, unknown>> {
  const info = await ensureEngine();
  const res = await fetch(`${info.baseUrl}/v1/jobs/${jobId}/events`, {
    headers: { Authorization: `Bearer ${info.token}` },
  });
  if (!res.ok || !res.body) throw new Error("SSE unavailable");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let last: Record<string, unknown> | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      const line = part
        .split("\n")
        .find((l) => l.startsWith("data: "));
      if (!line) continue;
      const data = JSON.parse(line.slice(6)) as Record<string, unknown>;
      if (!win.isDestroyed()) {
        win.webContents.send("job:progress", data);
      }
      last = data;
      if (data.type === "completed" || data.type === "failed" || data.type === "cancelled") {
        return (await getJob(jobId)) as Record<string, unknown>;
      }
    }
  }
  return last ? ((await getJob(jobId)) as Record<string, unknown>) : await getJob(jobId);
}

async function watchJobPoll(
  jobId: string,
  win: BrowserWindow,
  intervalMs: number,
): Promise<Record<string, unknown>> {
  for (;;) {
    const job = await getJob(jobId);
    if (!win.isDestroyed()) {
      win.webContents.send("job:progress", {
        type: "progress",
        job_id: jobId,
        progress: job.progress,
        stage: job.stage,
        message: job.message,
        state: job.state,
      });
    }
    const state = String(job.state);
    if (state === "completed" || state === "failed" || state === "cancelled") {
      return job;
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}

import { useEffect, useMemo, useRef, useState } from "react";

type Preset = "natural" | "balanced" | "enhanced";

type QueueItem = {
  id: string;
  path: string;
  name: string;
  jobId?: string;
  state: "idle" | "queued" | "running" | "completed" | "failed" | "cancelled";
  progress: number;
  stage: string;
  message: string;
  dfn?: boolean;
  label?: string;
  outputPath?: string;
  error?: string;
  restoredWav?: string;
  extractedWav?: string;
};

function basename(p: string) {
  return p.replace(/\\/g, "/").split("/").pop() ?? p;
}

function stem(p: string) {
  const n = basename(p);
  const i = n.lastIndexOf(".");
  return i >= 0 ? n.slice(0, i) : n;
}

export default function App() {
  const [items, setItems] = useState<QueueItem[]>([]);
  const [preset, setPreset] = useState<Preset>("balanced");
  const [strength, setStrength] = useState(0.6);
  const [loudness, setLoudness] = useState(-16);
  const [outputDir, setOutputDir] = useState("");
  const [busy, setBusy] = useState(false);
  const [engineReady, setEngineReady] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [abMode, setAbMode] = useState<"A" | "B">("B");
  const [loudnessMatch, setLoudnessMatch] = useState(true);
  const audioRef = useRef<HTMLAudioElement>(null);
  const cancelAllRef = useRef(false);

  const selected = useMemo(
    () => items.find((i) => i.id === selectedId) ?? null,
    [items, selectedId],
  );

  useEffect(() => {
    void window.audiorestorer.appInfo().then(async (info) => {
      const out = await window.audiorestorer.ensureOutputDir(info.defaultOutputDir);
      setOutputDir(out);
      setEngineReady(true);
    });
    const off = window.audiorestorer.onJobProgress((data) => {
      const jobId = String(data.job_id ?? "");
      setItems((prev) =>
        prev.map((it) => {
          if (it.jobId !== jobId) return it;
          const progress = Number(data.progress ?? it.progress);
          const type = String(data.type ?? "");
          let state = it.state;
          if (type === "progress" || type === "queued") state = progress > 0 ? "running" : "queued";
          if (type === "completed") state = "completed";
          if (type === "failed") state = "failed";
          if (type === "cancelled") state = "cancelled";
          return {
            ...it,
            progress,
            stage: String(data.stage ?? it.stage),
            message: String(data.message ?? it.message),
            state,
            error: data.error ? String(data.error) : it.error,
          };
        }),
      );
    });
    return off;
  }, []);

  function upsertFiles(paths: string[]) {
    setItems((prev) => {
      const existing = new Set(prev.map((p) => p.path));
      const next = [...prev];
      for (const path of paths) {
        if (existing.has(path)) continue;
        next.push({
          id: crypto.randomUUID(),
          path,
          name: basename(path),
          state: "idle",
          progress: 0,
          stage: "",
          message: "",
        });
      }
      return next;
    });
  }

  async function onImportFiles() {
    const paths = await window.audiorestorer.openMedia();
    upsertFiles(paths);
  }

  async function onImportFolder() {
    const folder = await window.audiorestorer.openFolder();
    if (!folder) return;
    const paths = await window.audiorestorer.listMediaInFolder(folder);
    upsertFiles(paths);
  }

  async function onChooseOutput() {
    const dir = await window.audiorestorer.chooseOutput();
    if (dir) {
      await window.audiorestorer.ensureOutputDir(dir);
      setOutputDir(dir);
    }
  }

  async function processQueue() {
    if (!items.length || busy) return;
    setBusy(true);
    cancelAllRef.current = false;
    const out = await window.audiorestorer.ensureOutputDir(outputDir || undefined);
    setOutputDir(out);

    for (const item of items) {
      if (cancelAllRef.current) break;
      if (item.state === "completed") continue;

      const outputPath = `${out}\\${stem(item.path)}.restored.mp4`;
      setItems((prev) =>
        prev.map((it) =>
          it.id === item.id
            ? { ...it, state: "queued", progress: 0, message: "Starting…", outputPath }
            : it,
        ),
      );

      try {
        const job = await window.audiorestorer.createJob({
          kind: "process",
          mediaPath: item.path,
          outputPath,
          settings: {
            preset,
            strength,
            loudness_target_lufs: loudness,
          },
        });
        const jobId = String(job.id);
        setItems((prev) =>
          prev.map((it) => (it.id === item.id ? { ...it, jobId, state: "running" } : it)),
        );
        const finalJob = await window.audiorestorer.watchJob(jobId);
        const result = finalJob.result as
          | {
              stages_applied?: string[];
              analysis?: { timeline?: { label?: string }[] };
              output_audio_path?: string;
              output_media_path?: string;
            }
          | undefined;
        const stages = result?.stages_applied ?? [];
        setItems((prev) =>
          prev.map((it) =>
            it.id === item.id
              ? {
                  ...it,
                  state: String(finalJob.state) as QueueItem["state"],
                  progress: Number(finalJob.progress ?? 1),
                  dfn: stages.includes("denoise_speech"),
                  label: result?.analysis?.timeline?.[0]?.label,
                  outputPath: result?.output_media_path ?? outputPath,
                  restoredWav: result?.output_audio_path,
                  error: finalJob.error ? String(finalJob.error) : undefined,
                }
              : it,
          ),
        );
      } catch (err) {
        setItems((prev) =>
          prev.map((it) =>
            it.id === item.id
              ? { ...it, state: "failed", error: String(err), message: String(err) }
              : it,
          ),
        );
      }
    }
    setBusy(false);
  }

  async function cancelSelected() {
    if (!selected?.jobId) return;
    await window.audiorestorer.cancelJob(selected.jobId);
  }

  function cancelAll() {
    cancelAllRef.current = true;
    for (const it of items) {
      if (it.jobId && (it.state === "running" || it.state === "queued")) {
        void window.audiorestorer.cancelJob(it.jobId);
      }
    }
  }

  useEffect(() => {
    const el = audioRef.current;
    if (!el || !selected) return;
    if (abMode === "B" && selected.restoredWav) {
      el.src = window.audiorestorer.toMediaUrl(selected.restoredWav);
      el.volume = loudnessMatch ? 1 : 1;
    } else if (abMode === "A") {
      // Prefer extracted wav from work dir convention if present
      const guess = selected.restoredWav
        ? selected.restoredWav.replace(/restored\.wav$/i, "extracted.wav")
        : "";
      if (guess) el.src = window.audiorestorer.toMediaUrl(guess);
    }
  }, [abMode, selected, loudnessMatch]);

  const stats = useMemo(() => {
    const total = items.length;
    const done = items.filter((i) => i.state === "completed").length;
    const failed = items.filter((i) => i.state === "failed").length;
    const dfn = items.filter((i) => i.dfn).length;
    return { total, done, failed, dfn };
  }, [items]);

  return (
    <div className="min-h-full flex flex-col">
      <header className="px-8 pt-7 pb-3 flex items-end justify-between gap-6">
        <div>
          <p className="text-[11px] tracking-[0.22em] uppercase text-[#9aa39a]">
            Windows · Offline · {engineReady ? "Engine ready" : "Starting engine…"}
          </p>
          <h1 className="text-3xl font-semibold tracking-tight text-[#e7e2d6] mt-1">
            AudioRestorer <span className="text-[#c4a35a]">AI</span>
          </h1>
        </div>
        <div className="text-right text-xs text-[#9aa39a]">
          <div>
            {stats.done}/{stats.total} done · {stats.failed} failed · DFN {stats.dfn}
          </div>
        </div>
      </header>

      <main className="flex-1 px-8 pb-8 grid grid-cols-1 xl:grid-cols-[1.15fr_0.85fr] gap-5">
        <section className="rounded-2xl border border-white/10 bg-[#171c19]/90 p-5 flex flex-col gap-4 min-h-[520px]">
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => void onImportFiles()}
              className="rounded-lg bg-[#c4a35a] text-[#0e1210] px-3 py-2 text-sm font-semibold"
            >
              Add files
            </button>
            <button
              type="button"
              onClick={() => void onImportFolder()}
              className="rounded-lg border border-white/15 px-3 py-2 text-sm"
            >
              Add folder
            </button>
            <button
              type="button"
              onClick={() => void processQueue()}
              disabled={!items.length || busy}
              className="rounded-lg bg-[#6fbf8a] text-[#0e1210] px-3 py-2 text-sm font-semibold disabled:opacity-40"
            >
              Process all
            </button>
            <button
              type="button"
              onClick={cancelAll}
              disabled={!busy}
              className="rounded-lg border border-red-400/40 text-red-200 px-3 py-2 text-sm disabled:opacity-40"
            >
              Cancel all
            </button>
            <button
              type="button"
              onClick={() => void onChooseOutput()}
              className="rounded-lg border border-white/15 px-3 py-2 text-sm"
            >
              Output folder
            </button>
          </div>

          <div className="text-xs text-[#9aa39a] break-all">Output: {outputDir || "…"}</div>

          <div className="grid grid-cols-3 gap-3">
            <label className="text-sm">
              <span className="text-[#9aa39a]">Preset</span>
              <select
                className="mt-1 w-full rounded-lg bg-[#0e1210] border border-white/10 px-2 py-2"
                value={preset}
                onChange={(e) => setPreset(e.target.value as Preset)}
              >
                <option value="natural">Natural</option>
                <option value="balanced">Balanced</option>
                <option value="enhanced">Enhanced</option>
              </select>
            </label>
            <label className="text-sm">
              <span className="text-[#9aa39a]">Strength {strength.toFixed(2)}</span>
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={strength}
                onChange={(e) => setStrength(Number(e.target.value))}
                className="mt-3 w-full"
              />
            </label>
            <label className="text-sm">
              <span className="text-[#9aa39a]">Loudness {loudness} LUFS</span>
              <input
                type="range"
                min={-23}
                max={-14}
                step={1}
                value={loudness}
                onChange={(e) => setLoudness(Number(e.target.value))}
                className="mt-3 w-full"
              />
            </label>
          </div>

          <div className="flex-1 overflow-auto rounded-xl border border-white/5">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-[#121714] text-[#9aa39a] text-left">
                <tr>
                  <th className="px-3 py-2 font-medium">File</th>
                  <th className="px-3 py-2 font-medium">Status</th>
                  <th className="px-3 py-2 font-medium">Progress</th>
                  <th className="px-3 py-2 font-medium">Tags</th>
                </tr>
              </thead>
              <tbody>
                {items.map((it) => (
                  <tr
                    key={it.id}
                    onClick={() => setSelectedId(it.id)}
                    className={`border-t border-white/5 cursor-pointer ${
                      selectedId === it.id ? "bg-white/5" : "hover:bg-white/[0.03]"
                    }`}
                  >
                    <td className="px-3 py-2 break-all">{it.name}</td>
                    <td className="px-3 py-2 capitalize">{it.state}</td>
                    <td className="px-3 py-2 min-w-[140px]">
                      <div className="h-2 rounded bg-black/40 overflow-hidden">
                        <div
                          className="h-full bg-[#6fbf8a]"
                          style={{ width: `${Math.round(it.progress * 100)}%` }}
                        />
                      </div>
                      <div className="text-[11px] text-[#9aa39a] mt-1">
                        {it.stage || it.message || "—"}
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      {it.dfn ? (
                        <span className="text-[11px] px-2 py-0.5 rounded bg-[#c4a35a]/20 text-[#c4a35a]">
                          DFN
                        </span>
                      ) : it.state === "completed" ? (
                        <span className="text-[11px] px-2 py-0.5 rounded bg-white/10">DSP</span>
                      ) : null}
                      {it.label ? (
                        <span className="ml-1 text-[11px] text-[#9aa39a]">{it.label}</span>
                      ) : null}
                    </td>
                  </tr>
                ))}
                {!items.length ? (
                  <tr>
                    <td colSpan={4} className="px-3 py-8 text-center text-[#9aa39a]">
                      Add files or a folder to start a batch.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </section>

        <section className="rounded-2xl border border-white/10 bg-[#171c19]/90 p-5 flex flex-col gap-4">
          <h2 className="text-sm tracking-wide uppercase text-[#9aa39a]">A/B preview</h2>
          {selected ? (
            <>
              <div className="text-sm break-all">{selected.name}</div>
              <div className="flex gap-2">
                <button
                  type="button"
                  className={`rounded-lg px-3 py-2 text-sm ${
                    abMode === "A" ? "bg-white/15" : "border border-white/15"
                  }`}
                  onClick={() => setAbMode("A")}
                >
                  A Original
                </button>
                <button
                  type="button"
                  className={`rounded-lg px-3 py-2 text-sm ${
                    abMode === "B" ? "bg-[#6fbf8a] text-[#0e1210] font-semibold" : "border border-white/15"
                  }`}
                  onClick={() => setAbMode("B")}
                >
                  B Restored
                </button>
                <label className="ml-auto flex items-center gap-2 text-xs text-[#9aa39a]">
                  <input
                    type="checkbox"
                    checked={loudnessMatch}
                    onChange={(e) => setLoudnessMatch(e.target.checked)}
                  />
                  Loudness match
                </label>
              </div>
              <audio ref={audioRef} controls className="w-full" />
              <div className="text-xs text-[#9aa39a] space-y-1">
                <div>Stage: {selected.stage || "—"}</div>
                <div>Message: {selected.message || selected.error || "—"}</div>
                {selected.outputPath ? (
                  <button
                    type="button"
                    className="underline"
                    onClick={() => void window.audiorestorer.showItem(selected.outputPath!)}
                  >
                    Show output
                  </button>
                ) : null}
              </div>
              <button
                type="button"
                onClick={() => void cancelSelected()}
                disabled={!selected.jobId || selected.state === "completed"}
                className="rounded-lg border border-white/15 px-3 py-2 text-sm disabled:opacity-40"
              >
                Cancel selected
              </button>
            </>
          ) : (
            <p className="text-sm text-[#9aa39a]">Select a queue item to preview A/B audio.</p>
          )}
          <p className="text-xs text-[#9aa39a] mt-auto">
            4K HEVC video is not played in-app (keeps UI smooth). Compare audio here, open the remuxed
            MP4 in your video player for picture + sound.
          </p>
        </section>
      </main>
    </div>
  );
}

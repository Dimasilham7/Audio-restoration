import { useEffect, useMemo, useRef, useState } from "react";
import {
  type AnalysisSnapshot,
  type PlanStage,
  type Preset,
  type QueueItem,
  type ScreenId,
  basename,
  confidenceBadge,
  stem,
} from "./types";

const NAV: { id: ScreenId; label: string }[] = [
  { id: "welcome", label: "Welcome" },
  { id: "import", label: "Import" },
  { id: "analysis", label: "Analysis" },
  { id: "diagnosis", label: "Diagnosis" },
  { id: "restore", label: "Restore" },
  { id: "ab", label: "A/B" },
  { id: "export", label: "Export" },
  { id: "models", label: "Models" },
  { id: "settings", label: "Settings" },
];

export default function App() {
  const [screen, setScreen] = useState<ScreenId>("welcome");
  const [items, setItems] = useState<QueueItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [preset, setPreset] = useState<Preset>("balanced");
  const [strength, setStrength] = useState(0.7);
  const [loudness, setLoudness] = useState(-16);
  const [speechClarity, setSpeechClarity] = useState(0.55);
  const [ambience, setAmbience] = useState(0.5);
  const [noiseReduction, setNoiseReduction] = useState(0.55);
  const [trebleRecovery, setTrebleRecovery] = useState(0.6);
  const [musicEnhancement, setMusicEnhancement] = useState(0.55);
  const [outputDir, setOutputDir] = useState("");
  const [busy, setBusy] = useState(false);
  const [engineReady, setEngineReady] = useState(false);
  const [projects, setProjects] = useState<Record<string, unknown>[]>([]);
  const [models, setModels] = useState<Record<string, unknown>[]>([]);
  const [schemaVersions, setSchemaVersions] = useState<number[]>([]);
  const [device, setDevice] = useState("auto");
  const [abMode, setAbMode] = useState<"A" | "B">("B");
  // Off by default: matching often masks EQ/NR differences in A/B
  const [loudnessMatch, setLoudnessMatch] = useState(false);
  const [advanced, setAdvanced] = useState(false);
  const [toasts, setToasts] = useState<string[]>([]);
  const audioRef = useRef<HTMLAudioElement>(null);
  const cancelAllRef = useRef(false);

  const selected = useMemo(
    () => items.find((i) => i.id === selectedId) ?? null,
    [items, selectedId],
  );
  const contentLabel = selected?.label ?? "mixed";

  function toast(msg: string) {
    setToasts((t) => [msg, ...t].slice(0, 4));
  }

  function applyPresetDefaults(next: Preset) {
    setPreset(next);
    if (next === "natural") {
      setStrength(0.4);
      setNoiseReduction(0.35);
      setTrebleRecovery(0.35);
      setSpeechClarity(0.4);
      setAmbience(0.75);
      setMusicEnhancement(0.35);
    } else if (next === "balanced") {
      setStrength(0.7);
      setNoiseReduction(0.55);
      setTrebleRecovery(0.6);
      setSpeechClarity(0.55);
      setAmbience(0.5);
      setMusicEnhancement(0.55);
    } else {
      setStrength(0.9);
      setNoiseReduction(0.8);
      setTrebleRecovery(0.85);
      setSpeechClarity(0.75);
      setAmbience(0.3);
      setMusicEnhancement(0.75);
    }
  }

  function restorationSettings() {
    return {
      preset,
      strength,
      loudness_target_lufs: loudness,
      noise_reduction: noiseReduction,
      speech_clarity: speechClarity,
      ambience_preservation: ambience,
      treble_recovery: trebleRecovery,
      music_enhancement: musicEnhancement,
    };
  }

  useEffect(() => {
    void (async () => {
      const info = await window.audiorestorer.appInfo();
      const out = await window.audiorestorer.ensureOutputDir(info.defaultOutputDir);
      setOutputDir(out);
      setEngineReady(true);
      setProjects(await window.audiorestorer.listProjects());
      setModels(await window.audiorestorer.listModels());
      setSchemaVersions(await window.audiorestorer.schemaVersions());
      const settings = await window.audiorestorer.getSettings();
      if (settings.preset) setPreset(settings.preset as Preset);
      if (typeof settings.loudness === "number") setLoudness(settings.loudness);
      if (typeof settings.device === "string") setDevice(settings.device);
    })();
    return window.audiorestorer.onJobProgress((data) => {
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
  }, []);

  useEffect(() => {
    const el = audioRef.current;
    if (!el || !selected?.restoredWav) return;
    const path =
      abMode === "B"
        ? selected.restoredWav
        : selected.restoredWav.replace(/restored\.wav$/i, "extracted.wav");
    el.src = window.audiorestorer.toMediaUrl(path);
  }, [abMode, selected, loudnessMatch]);

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
    if (paths[0]) setSelectedId((id) => id ?? crypto.randomUUID());
  }

  async function onImportFiles() {
    const paths = await window.audiorestorer.openMedia();
    upsertFiles(paths);
    if (paths.length) {
      setSelectedId(
        (prev) => items.find((i) => i.path === paths[0])?.id ?? prev ?? crypto.randomUUID(),
      );
      // re-resolve after state update via path
      setItems((prev) => {
        const match = prev.find((i) => i.path === paths[0]);
        if (match) setSelectedId(match.id);
        return prev;
      });
      setScreen("import");
      toast(`Imported ${paths.length} file(s)`);
    }
  }

  async function onImportFolder() {
    const folder = await window.audiorestorer.openFolder();
    if (!folder) return;
    const paths = await window.audiorestorer.listMediaInFolder(folder);
    upsertFiles(paths);
    setScreen("import");
    toast(`Imported folder (${paths.length} media)`);
  }

  async function createProject() {
    const folder = await window.audiorestorer.openFolder();
    if (!folder) return;
    const name = basename(folder);
    await window.audiorestorer.createProject(name, folder);
    setProjects(await window.audiorestorer.listProjects());
    toast(`Project “${name}” created`);
  }

  async function analyzeSelected() {
    if (!selected) return;
    setBusy(true);
    setScreen("analysis");
    try {
      const job = await window.audiorestorer.createJob({
        kind: "analyze",
        mediaPath: selected.path,
      });
      const jobId = String(job.id);
      setItems((prev) =>
        prev.map((it) => (it.id === selected.id ? { ...it, jobId, state: "running" } : it)),
      );
      const finalJob = await window.audiorestorer.watchJob(jobId);
      const result = finalJob.result as {
        analysis?: Record<string, unknown>;
        plan?: { stages?: PlanStage[] };
      };
      const analysisRaw = result?.analysis ?? {};
      const issues = (analysisRaw.issues as AnalysisSnapshot["issues"]) ?? [];
      const timeline = analysisRaw.timeline as AnalysisSnapshot["timeline"];
      const gm = analysisRaw.global_metrics as { loudness?: AnalysisSnapshot["loudness"] };
      setItems((prev) =>
        prev.map((it) =>
          it.id === selected.id
            ? {
                ...it,
                state: "completed",
                progress: 1,
                analysis: {
                  issues,
                  timeline,
                  loudness: gm?.loudness,
                },
                planStages: result?.plan?.stages ?? [],
                label: timeline?.[0]?.label,
              }
            : it,
        ),
      );
      setScreen("diagnosis");
      toast("Analysis complete — review diagnosis");
    } catch (e) {
      toast(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function processQueue() {
    if (!items.length || busy) return;
    setBusy(true);
    cancelAllRef.current = false;
    setScreen("restore");
    const out = await window.audiorestorer.ensureOutputDir(outputDir || undefined);
    setOutputDir(out);
    for (const item of items) {
      if (cancelAllRef.current) break;
      if (item.state === "completed" && item.outputPath) continue;
      const outputPath = `${out}\\${stem(item.path)}.restored.mp4`;
      try {
        const job = await window.audiorestorer.createJob({
          kind: "process",
          mediaPath: item.path,
          outputPath,
          settings: restorationSettings(),
        });
        const jobId = String(job.id);
        setItems((prev) =>
          prev.map((it) =>
            it.id === item.id ? { ...it, jobId, state: "running", outputPath } : it,
          ),
        );
        const finalJob = await window.audiorestorer.watchJob(jobId);
        const result = finalJob.result as {
          stages_applied?: string[];
          analysis?: { timeline?: { label?: string }[]; issues?: AnalysisSnapshot["issues"] };
          plan?: { stages?: PlanStage[] };
          output_audio_path?: string;
          output_media_path?: string;
        };
        setItems((prev) =>
          prev.map((it) =>
            it.id === item.id
              ? {
                  ...it,
                  state: String(finalJob.state) as QueueItem["state"],
                  progress: Number(finalJob.progress ?? 1),
                  dfn: (result?.stages_applied ?? []).includes("denoise_speech"),
                  label: result?.analysis?.timeline?.[0]?.label,
                  outputPath: result?.output_media_path ?? outputPath,
                  restoredWav: result?.output_audio_path,
                  analysis: result?.analysis
                    ? {
                        issues: result.analysis.issues ?? [],
                        timeline: result.analysis.timeline,
                      }
                    : it.analysis,
                  planStages: result?.plan?.stages ?? it.planStages,
                  error: finalJob.error ? String(finalJob.error) : undefined,
                }
              : it,
          ),
        );
      } catch (err) {
        setItems((prev) =>
          prev.map((it) =>
            it.id === item.id ? { ...it, state: "failed", error: String(err) } : it,
          ),
        );
      }
    }
    setBusy(false);
    setScreen("ab");
    toast("Batch finished");
  }

  async function saveSettings() {
    await window.audiorestorer.setSettings({ preset, loudness, device, strength });
    toast("Settings saved");
  }

  const showSpeech = contentLabel !== "music_dominant" || advanced;
  const showMusic = contentLabel !== "speech_dominant" || advanced;

  return (
    <div className="min-h-full flex flex-col">
      <header className="px-6 pt-5 pb-3 flex items-end justify-between gap-4 border-b border-white/5">
        <div>
          <p className="text-[11px] tracking-[0.22em] uppercase text-[#9aa39a]">
            Offline · {engineReady ? "Engine ready" : "Starting…"} · SQLite{" "}
            {schemaVersions.length ? `v${schemaVersions.join(",")}` : "…"}
          </p>
          <h1 className="text-2xl font-semibold tracking-tight text-[#e7e2d6] mt-1">
            AudioRestorer <span className="text-[#c4a35a]">AI</span>
          </h1>
        </div>
        <div className="flex flex-wrap gap-1 justify-end max-w-[55%]">
          {NAV.map((n) => (
            <button
              key={n.id}
              type="button"
              onClick={() => setScreen(n.id)}
              className={`text-xs px-2.5 py-1.5 rounded-lg ${
                screen === n.id ? "bg-[#c4a35a] text-[#0e1210] font-semibold" : "border border-white/10"
              }`}
            >
              {n.label}
            </button>
          ))}
        </div>
      </header>

      {toasts.length ? (
        <div className="px-6 pt-2 space-y-1">
          {toasts.map((t, i) => (
            <div key={`${t}-${i}`} className="text-xs text-[#c4a35a] bg-[#c4a35a]/10 rounded px-3 py-1">
              {t}
            </div>
          ))}
        </div>
      ) : null}

      <main className="flex-1 px-6 py-5 overflow-auto">
        {screen === "welcome" && (
          <section className="space-y-4 max-w-4xl">
            <p className="text-[#9aa39a] text-sm">
              Local-first restoration. Import media, review honest diagnosis, restore, A/B, export.
            </p>
            <div className="flex gap-2">
              <button type="button" className="rounded-lg bg-[#c4a35a] text-[#0e1210] px-4 py-2 font-semibold" onClick={() => void onImportFiles()}>
                Import media
              </button>
              <button type="button" className="rounded-lg border border-white/15 px-4 py-2" onClick={() => void createProject()}>
                New project
              </button>
              <button type="button" className="rounded-lg border border-white/15 px-4 py-2" onClick={() => setScreen("models")}>
                Models
              </button>
            </div>
            <div>
              <h2 className="text-sm uppercase tracking-wide text-[#9aa39a] mb-2">Recent projects</h2>
              <div className="grid gap-2 sm:grid-cols-2">
                {projects.map((p) => (
                  <div key={String(p.id)} className="rounded-xl border border-white/10 p-3">
                    <div className="font-medium">{String(p.name)}</div>
                    <div className="text-xs text-[#9aa39a] break-all">{String(p.root_path)}</div>
                  </div>
                ))}
                {!projects.length ? <p className="text-sm text-[#9aa39a]">No projects yet.</p> : null}
              </div>
            </div>
            <div className="flex gap-2 text-xs">
              <span className="px-2 py-1 rounded bg-[#6fbf8a]/15 text-[#6fbf8a]">Engine {engineReady ? "running" : "…"}</span>
              <span className="px-2 py-1 rounded bg-white/10">Device {device.toUpperCase()}</span>
              <span className="px-2 py-1 rounded bg-white/10">Models {models.filter((m) => m.state === "installed").length}/{models.length}</span>
            </div>
          </section>
        )}

        {screen === "import" && (
          <section className="space-y-4">
            <div className="flex gap-2">
              <button type="button" className="rounded-lg bg-[#c4a35a] text-[#0e1210] px-3 py-2 text-sm font-semibold" onClick={() => void onImportFiles()}>Add files</button>
              <button type="button" className="rounded-lg border border-white/15 px-3 py-2 text-sm" onClick={() => void onImportFolder()}>Add folder</button>
              <button type="button" className="rounded-lg bg-[#6fbf8a] text-[#0e1210] px-3 py-2 text-sm font-semibold disabled:opacity-40" disabled={!selected} onClick={() => void analyzeSelected()}>Continue → Analyze</button>
            </div>
            <ul className="space-y-2">
              {items.map((it) => (
                <li key={it.id}>
                  <button type="button" onClick={() => setSelectedId(it.id)} className={`w-full text-left rounded-xl border px-3 py-2 ${selectedId === it.id ? "border-[#c4a35a] bg-white/5" : "border-white/10"}`}>
                    <div className="text-sm">{it.name}</div>
                    <div className="text-xs text-[#9aa39a] break-all">{it.path}</div>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        {screen === "analysis" && (
          <section className="space-y-4 max-w-3xl">
            <h2 className="text-lg">Analysis workspace</h2>
            <p className="text-sm text-[#9aa39a]">Video is not decoded in-app (4K HEVC). Waveform uses extracted audio after restore.</p>
            {selected ? (
              <>
                <div className="text-sm">{selected.name}</div>
                <div className="h-2 rounded bg-black/40 overflow-hidden">
                  <div className="h-full bg-[#6fbf8a]" style={{ width: `${Math.round(selected.progress * 100)}%` }} />
                </div>
                <div className="text-xs text-[#9aa39a]">{selected.stage || selected.message || "Idle"}</div>
                <button type="button" className="rounded-lg bg-[#6fbf8a] text-[#0e1210] px-3 py-2 text-sm font-semibold disabled:opacity-40" disabled={busy} onClick={() => void analyzeSelected()}>
                  {busy ? "Running…" : "Run analysis"}
                </button>
              </>
            ) : (
              <p className="text-sm text-[#9aa39a]">Import a file first.</p>
            )}
          </section>
        )}

        {screen === "diagnosis" && (
          <section className="space-y-4 max-w-3xl">
            <h2 className="text-lg">Diagnosis</h2>
            {selected?.analysis ? (
              <>
                <div className="text-sm">
                  Content: <span className="text-[#c4a35a]">{selected.label ?? "unknown"}</span>
                  {selected.analysis.timeline?.[0]?.content ? (
                    <span className="text-[#9aa39a] ml-2 text-xs">
                      speech={Number(selected.analysis.timeline[0].content.speech ?? 0).toFixed(2)} · music=
                      {Number(selected.analysis.timeline[0].content.music ?? 0).toFixed(2)}
                    </span>
                  ) : null}
                </div>
                <div className="space-y-2">
                  {selected.analysis.issues.map((issue) => {
                    const conf = confidenceBadge(issue.confidence);
                    return (
                      <div key={issue.id} className="rounded-xl border border-white/10 p-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-medium capitalize">{issue.id.replaceAll("_", " ")}</span>
                          <span className={`text-[11px] px-2 py-0.5 rounded ${conf.className}`}>Confidence {conf.label}</span>
                          <span className="text-[11px] px-2 py-0.5 rounded bg-white/10 capitalize">{issue.recoverability}</span>
                        </div>
                        <p className="text-sm text-[#9aa39a] mt-1">{issue.user_message}</p>
                      </div>
                    );
                  })}
                  {!selected.analysis.issues.length ? <p className="text-sm text-[#9aa39a]">No major issues flagged.</p> : null}
                </div>
                <div>
                  <h3 className="text-sm text-[#9aa39a] mb-1">Recommended stages</h3>
                  <ul className="text-sm space-y-1">
                    {(selected.planStages ?? []).filter((s) => s.enabled).map((s) => (
                      <li key={s.id}>• {s.id}: {s.reason}</li>
                    ))}
                  </ul>
                </div>
                <button type="button" className="rounded-lg bg-[#6fbf8a] text-[#0e1210] px-3 py-2 text-sm font-semibold" onClick={() => setScreen("restore")}>
                  Continue with {preset}
                </button>
              </>
            ) : (
              <p className="text-sm text-[#9aa39a]">Run analysis first.</p>
            )}
          </section>
        )}

        {screen === "restore" && (
          <section className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 max-w-4xl">
              <label className="text-sm">Preset
                <select className="mt-1 w-full rounded-lg bg-[#0e1210] border border-white/10 px-2 py-2" value={preset} onChange={(e) => applyPresetDefaults(e.target.value as Preset)}>
                  <option value="natural">Natural</option>
                  <option value="balanced">Balanced</option>
                  <option value="enhanced">Enhanced</option>
                </select>
              </label>
              <label className="text-sm">Strength {strength.toFixed(2)}
                <input type="range" min={0} max={1} step={0.05} value={strength} onChange={(e) => setStrength(Number(e.target.value))} className="mt-3 w-full" />
              </label>
              <label className="text-sm">Loudness {loudness} LUFS
                <input type="range" min={-23} max={-14} step={1} value={loudness} onChange={(e) => setLoudness(Number(e.target.value))} className="mt-3 w-full" />
              </label>
              {showSpeech ? (
                <label className="text-sm">Speech clarity {speechClarity.toFixed(2)}
                  <input type="range" min={0} max={1} step={0.05} value={speechClarity} onChange={(e) => setSpeechClarity(Number(e.target.value))} className="mt-3 w-full" />
                </label>
              ) : null}
              <label className="text-sm">Ambience preservation {ambience.toFixed(2)}
                <input type="range" min={0} max={1} step={0.05} value={ambience} onChange={(e) => setAmbience(Number(e.target.value))} className="mt-3 w-full" />
              </label>
              <label className="text-sm">Noise reduction {noiseReduction.toFixed(2)}
                <input type="range" min={0} max={1} step={0.05} value={noiseReduction} onChange={(e) => setNoiseReduction(Number(e.target.value))} className="mt-3 w-full" />
              </label>
              {showMusic || advanced ? (
                <label className="text-sm">Music enhancement {musicEnhancement.toFixed(2)}
                  <input type="range" min={0} max={1} step={0.05} value={musicEnhancement} onChange={(e) => setMusicEnhancement(Number(e.target.value))} className="mt-3 w-full" />
                </label>
              ) : null}
              {advanced ? (
                <label className="text-sm">Treble recovery {trebleRecovery.toFixed(2)}
                  <input type="range" min={0} max={1} step={0.05} value={trebleRecovery} onChange={(e) => setTrebleRecovery(Number(e.target.value))} className="mt-3 w-full" />
                </label>
              ) : null}
            </div>
            <label className="flex items-center gap-2 text-xs text-[#9aa39a]">
              <input type="checkbox" checked={advanced} onChange={(e) => setAdvanced(e.target.checked)} /> Show advanced / all macros
            </label>
            {contentLabel === "music_dominant" ? (
              <p className="text-xs text-[#c4a35a]">Speech enhancer blocked on music-dominant regions unless gated.</p>
            ) : null}
            <div className="flex gap-2">
              <button type="button" className="rounded-lg bg-[#6fbf8a] text-[#0e1210] px-3 py-2 text-sm font-semibold disabled:opacity-40" disabled={!items.length || busy} onClick={() => void processQueue()}>
                Restore full / Process all
              </button>
              <button type="button" className="rounded-lg border border-red-400/40 text-red-200 px-3 py-2 text-sm" onClick={() => { cancelAllRef.current = true; toast("Cancel requested"); }}>
                Cancel all
              </button>
            </div>
            <QueueTable items={items} selectedId={selectedId} onSelect={setSelectedId} />
          </section>
        )}

        {screen === "ab" && (
          <section className="space-y-4 max-w-2xl">
            <h2 className="text-lg">A/B preview</h2>
            {selected ? (
              <>
                <div className="text-sm break-all">{selected.name}</div>
                <div className="flex gap-2 items-center">
                  <button type="button" className={`rounded-lg px-3 py-2 text-sm ${abMode === "A" ? "bg-white/15" : "border border-white/15"}`} onClick={() => setAbMode("A")}>A Original</button>
                  <button type="button" className={`rounded-lg px-3 py-2 text-sm ${abMode === "B" ? "bg-[#6fbf8a] text-[#0e1210] font-semibold" : "border border-white/15"}`} onClick={() => setAbMode("B")}>B Restored</button>
                  <label className="ml-auto flex items-center gap-2 text-xs text-[#9aa39a]" title="Matching level often hides EQ/NR changes">
                    <input type="checkbox" checked={loudnessMatch} onChange={(e) => setLoudnessMatch(e.target.checked)} /> Loudness match
                  </label>
                </div>
                <audio ref={audioRef} controls className="w-full" />
                <p className="text-xs text-[#9aa39a]">
                  Tip: leave Loudness match off to hear EQ/noise changes. Use Enhanced for a stronger A/B.
                  {loudnessMatch ? " Match on ≈ same loudness — differences can sound subtle." : ""}
                </p>
                <button type="button" className="rounded-lg bg-[#c4a35a] text-[#0e1210] px-3 py-2 text-sm font-semibold" onClick={() => setScreen("export")}>Approve & export</button>
              </>
            ) : (
              <p className="text-sm text-[#9aa39a]">Select a restored item.</p>
            )}
          </section>
        )}

        {screen === "export" && (
          <section className="space-y-4 max-w-xl">
            <h2 className="text-lg">Export center</h2>
            <p className="text-sm text-[#9aa39a]">Mode: Video remux (stream-copy) · AAC audio. Output folder below.</p>
            <div className="text-xs break-all">Output: {outputDir}</div>
            <button type="button" className="rounded-lg border border-white/15 px-3 py-2 text-sm" onClick={async () => {
              const dir = await window.audiorestorer.chooseOutput();
              if (dir) { await window.audiorestorer.ensureOutputDir(dir); setOutputDir(dir); }
            }}>Choose output folder</button>
            {selected?.outputPath ? (
              <div className="space-y-2">
                <div className="flex gap-2 text-xs">
                  <span className="px-2 py-1 rounded bg-[#6fbf8a]/20 text-[#6fbf8a]">sync OK</span>
                  <span className="px-2 py-1 rounded bg-white/10">restored ready</span>
                </div>
                <button type="button" className="underline text-sm" onClick={() => void window.audiorestorer.showItem(selected.outputPath!)}>Show in folder</button>
              </div>
            ) : (
              <p className="text-sm text-[#9aa39a]">Restore a file to export.</p>
            )}
          </section>
        )}

        {screen === "models" && (
          <section className="space-y-4">
            <h2 className="text-lg">Model management</h2>
            <table className="w-full text-sm">
              <thead className="text-[#9aa39a] text-left">
                <tr><th className="py-2">Name</th><th>Phase</th><th>State</th><th>License</th></tr>
              </thead>
              <tbody>
                {models.map((m) => (
                  <tr key={String(m.id)} className="border-t border-white/5">
                    <td className="py-2">{String(m.name)}</td>
                    <td>{String(m.phase).toUpperCase()}</td>
                    <td>{String(m.state)}</td>
                    <td className="text-xs text-[#9aa39a]">{String(m.license_notice)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="text-xs text-[#9aa39a]">V2 Demucs / V3 AudioSR stay optional — accept license notice before install (not bundled).</p>
          </section>
        )}

        {screen === "settings" && (
          <section className="space-y-4 max-w-md">
            <h2 className="text-lg">Settings</h2>
            <label className="text-sm block">Device
              <select className="mt-1 w-full rounded-lg bg-[#0e1210] border border-white/10 px-2 py-2" value={device} onChange={(e) => setDevice(e.target.value)}>
                <option value="auto">Auto</option>
                <option value="cpu">CPU</option>
                <option value="cuda">CUDA</option>
              </select>
            </label>
            <label className="text-sm block">Default preset
              <select className="mt-1 w-full rounded-lg bg-[#0e1210] border border-white/10 px-2 py-2" value={preset} onChange={(e) => applyPresetDefaults(e.target.value as Preset)}>
                <option value="natural">Natural</option>
                <option value="balanced">Balanced</option>
                <option value="enhanced">Enhanced</option>
              </select>
            </label>
            <button type="button" className="rounded-lg bg-[#c4a35a] text-[#0e1210] px-3 py-2 text-sm font-semibold" onClick={() => void saveSettings()}>Save</button>
            <p className="text-xs text-[#9aa39a]">About: AudioRestorer AI · GPL-3.0-or-later · FFmpeg GPL essentials shipped with installer.</p>
          </section>
        )}
      </main>
    </div>
  );
}

function QueueTable({
  items,
  selectedId,
  onSelect,
}: {
  items: QueueItem[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="overflow-auto rounded-xl border border-white/5">
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
            <tr key={it.id} onClick={() => onSelect(it.id)} className={`border-t border-white/5 cursor-pointer ${selectedId === it.id ? "bg-white/5" : ""}`}>
              <td className="px-3 py-2 break-all">{it.name}</td>
              <td className="px-3 py-2 capitalize">{it.state}</td>
              <td className="px-3 py-2 min-w-[140px]">
                <div className="h-2 rounded bg-black/40 overflow-hidden">
                  <div className="h-full bg-[#6fbf8a]" style={{ width: `${Math.round(it.progress * 100)}%` }} />
                </div>
              </td>
              <td className="px-3 py-2 text-xs">
                {it.dfn ? <span className="px-2 py-0.5 rounded bg-[#c4a35a]/20 text-[#c4a35a]">DFN</span> : null}
                {it.label ? <span className="ml-1 text-[#9aa39a]">{it.label}</span> : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

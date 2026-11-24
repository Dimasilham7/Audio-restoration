export type ScreenId =
  | "welcome"
  | "import"
  | "analysis"
  | "diagnosis"
  | "restore"
  | "ab"
  | "export"
  | "models"
  | "settings";

export type Preset = "natural" | "balanced" | "enhanced";

export type QueueItem = {
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
  analysis?: AnalysisSnapshot;
  planStages?: PlanStage[];
};

export type AnalysisSnapshot = {
  issues: Array<{
    id: string;
    severity: number;
    confidence: number;
    recoverability: string;
    user_message: string;
  }>;
  timeline?: Array<{ label?: string; content?: Record<string, number> }>;
  loudness?: { integrated_lufs?: number; true_peak_dbtp?: number };
};

export type PlanStage = {
  id: string;
  enabled: boolean;
  reason: string;
  confidence?: number;
};

export function basename(p: string) {
  return p.replace(/\\/g, "/").split("/").pop() ?? p;
}

export function stem(p: string) {
  const n = basename(p);
  const i = n.lastIndexOf(".");
  return i >= 0 ? n.slice(0, i) : n;
}

export function confidenceBadge(c: number): { label: string; className: string } {
  if (c >= 0.75) return { label: "High", className: "bg-[#6fbf8a]/20 text-[#6fbf8a]" };
  if (c >= 0.4) return { label: "Medium", className: "bg-[#c4a35a]/20 text-[#c4a35a]" };
  return { label: "Low", className: "bg-white/10 text-[#9aa39a]" };
}

import { z } from "zod";

export const PresetSchema = z.enum(["natural", "balanced", "enhanced"]);
export type Preset = z.infer<typeof PresetSchema>;

export const ProcessRequestSchema = z.object({
  inputPath: z.string().min(1),
  outputPath: z.string().optional(),
  preset: PresetSchema.default("balanced"),
  strength: z.number().min(0).max(1).default(0.6),
  loudnessTargetLufs: z.number().default(-16),
});
export type ProcessRequest = z.infer<typeof ProcessRequestSchema>;

export const AnalyzeRequestSchema = z.object({
  inputPath: z.string().min(1),
});
export type AnalyzeRequest = z.infer<typeof AnalyzeRequestSchema>;

export interface EngineHealth {
  status: string;
  version: string;
}

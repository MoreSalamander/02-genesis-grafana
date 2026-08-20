import type { RuntimeProof } from "@/lib/alive";

export interface SystemStatus {
  system: string; banner: string; grafana_live: boolean; gemini_live: boolean; investigations: number;
  /** Substrate states for the runtime-proof footer (app/runtime_proof.py). */
  runtime_proof?: RuntimeProof;
}
export interface InvestigationSummary {
  id: string; question: string; status: string; severity: string | null;
  leading_cause: string | null; confidence: number | null; escalated: boolean;
  created_at: string; updated_at: string;
}
export interface Stage { name: string; detail: string; at: string }
export interface TelemetryEvidence {
  id: string; kind: string; name: string; query: string; unit: string;
  latest: number | null; average: number | null; slope_per_min: number | null;
  samples: [number, number][]; lines: string[]; anomalous: boolean; detail: string;
  /** The API sends these; the console needs them to say *when* a reading is
   *  from. These are a snapshot over a window, not a live feed, and a farm
   *  dashboard that implies otherwise is lying about how fresh it is. */
  window_minutes?: number; retrieved_at?: string; source?: string;
  /** Deep link to the Grafana panel this signal lives on — the brief's
   *  "generate links back to Grafana for human review", per evidence item. */
  link?: string;
}
export interface CausalHypothesis {
  chain: string[]; rationale: string; related: boolean; validated: boolean; validation_notes: string;
}
export interface DiagnosisHypothesis {
  id: string; cause: string; confidence: number; supporting_evidence_ids: string[];
  contradicting_evidence_ids: string[]; contradiction_notes: string; severity: string; affected: string;
}
export interface RiskProjection { event: string; eta_minutes: number | null; at_risk: string; basis: string }
export interface RemediationPlan {
  action: string; expected_effects: string[]; risk: string; actuation: Record<string, unknown>;
  decision: string | null; decided_at: string | null;
}
export interface VerificationResult {
  improved: boolean; before: Record<string, number>; after: Record<string, number>; notes: string;
}
export interface InvestigationDetail {
  id: string; question: string; status: string; scope: string[]; error: string;
  stages: Stage[]; evidence: TelemetryEvidence[]; correlation: CausalHypothesis | null;
  diagnoses: DiagnosisHypothesis[]; leading_diagnosis_id: string | null;
  projection: RiskProjection | null; plan: RemediationPlan | null;
  verification: VerificationResult | null; escalated: boolean; escalation_reason: string;
  /** Present when a firing Grafana alert opened this investigation itself —
   *  the provenance the console leads with. */
  trigger?: {
    source: string; alertname: string; summary?: string; fingerprint?: string;
    labels?: Record<string, string>; incident_id?: string; starts_at?: string;
  } | null;
  /** The marks the agent wrote onto the dashboards as it worked. */
  annotations_written?: string[];
  created_at: string; updated_at: string;
}

export interface SlateTitle {
  key: string; name: string; kind: string; priority: number;
  frames_total: number; frames_done: number; progress: number;
  throughput_fpm: number; due_hours: number; risk_hours: number; status: string;
}
export interface SlateView {
  titles: SlateTitle[]; dailies_surge: boolean; sim_hour_of_day: number;
  hot_shots: { id: string; show: string; shot: string; frames: number; retake: boolean; waiting_s: number }[];
}
export interface EventRecord { event: string; at: string; investigation_id?: string; [k: string]: unknown }

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { cache: "no-store", ...init });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

export const getStatus = () => api<SystemStatus>("/api/status");
export const listInvestigations = () => api<InvestigationSummary[]>("/api/investigations");
export const getInvestigation = (id: string) => api<InvestigationDetail>(`/api/investigations/${id}`);
export const getEvents = (limit = 200) => api<EventRecord[]>(`/api/events?limit=${limit}`);
export const startInvestigation = (question: string) =>
  api<{ id: string }>("/api/investigations", {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ question }),
  });
export const decideInvestigation = (id: string, decision: "approved" | "rejected") =>
  api<unknown>(`/api/investigations/${id}/decision`, {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ decision }),
  });
/** End a run and remove it. A run still mid-loop is ended, not just hidden. */
export const clearInvestigation = (id: string) =>
  api<{ id: string; removed: boolean; was: string; was_running: boolean }>(
    `/api/investigations/${id}`, { method: "DELETE" });
export const simulateIncident = () =>
  api<unknown>("/sim/scenario/degrade", { method: "POST" });

export const ACTIVE = new Set(["OBSERVING", "CORRELATING", "DIAGNOSING", "PREDICTING", "ACTING", "VERIFYING"]);

/* --- the render farm itself ------------------------------------------------
   Distinct from everything above: these are the farm's own numbers, not the
   agent's findings. The console keeps them visually and verbally separate so
   nobody reads "the farm is on fire" as "the system concluded the farm is on
   fire". */

export interface FarmJob { id: string; frames: number; vram_gb: number; progress: number }
export interface FarmWorker {
  id: string; pool: string; state: string; gpu: number; temp_c: number;
  vram_gb: number; note: string; completed: number; failed: number;
  job: FarmJob | null;
}
export interface FarmIncident { key: string; label: string; blurb: string; signature: string }
export interface FarmView {
  mode: string; incident: string | null; incident_label: string | null; auto: boolean;
  queue: number; gpu: number; latency_s: number; concurrency_factor: number;
  workers: FarmWorker[];
  queued: { id: string; frames: number; vram_gb: number }[];
  queued_total: number;
  recent: { id: string; state: string; worker: string | null; note: string }[];
  completed_total: number; failed_total: number;
  recent_done: number; recent_failed: number;
  incidents: FarmIncident[];
}

export const getFarm = () => api<FarmView>("/api/farm");
export const getSlate = () => api<SlateView>("/api/slate");

/* --- the split mind: cognition (the agent thinking) and perception (what
       the system saw through Grafana MCP to think it) -------------------- */
export interface CognitionRecord {
  id: string; at: string; ref: string | null; role: string; model: string;
  live: boolean; ms: number; parsed_ok: boolean; error: string;
  tokens: { prompt?: number; total?: number };
  prompt_chars: number; raw_chars: number; preview: string;
}
export interface PerceptionRecord {
  at: string; tool: string; ms: number; ok: boolean; note: string; ref: string;
}
export const getCognition = (limit = 24, ref = "") =>
  api<CognitionRecord[]>(`/api/cognition?limit=${limit}${ref ? `&ref=${ref}` : ""}`);
export const getPerception = (limit = 40) =>
  api<PerceptionRecord[]>(`/api/perception?limit=${limit}`);
export const startScenario = (key: string) =>
  api<Record<string, unknown>>(`/api/farm/scenario/${key}`, { method: "POST" });
export const setFarmAuto = (on: boolean) =>
  api<Record<string, unknown>>(`/api/farm/auto/${on ? "on" : "off"}`, { method: "POST" });

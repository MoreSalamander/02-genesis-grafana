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
  created_at: string; updated_at: string;
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
export const simulateIncident = () =>
  api<unknown>("/sim/scenario/degrade", { method: "POST" });

export const ACTIVE = new Set(["OBSERVING", "CORRELATING", "DIAGNOSING", "PREDICTING", "ACTING", "VERIFYING"]);

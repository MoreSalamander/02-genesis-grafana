const SEVERITY: Record<string, string> = { LOW: "good", MEDIUM: "warn", HIGH: "crit", CRITICAL: "crit" };

export function SeverityChip({ severity }: { severity: string | null }) {
  if (!severity) return null;
  return <span className={`chip ${SEVERITY[severity] ?? ""}`}>▲ {severity}</span>;
}

const STATUS: Record<string, { cls: string; icon: string }> = {
  AWAITING_AUTHORIZATION: { cls: "accent", icon: "◆" },
  REMEDIATED: { cls: "good", icon: "✓" },
  REMEDIATION_FAILED: { cls: "crit", icon: "✕" },
  REJECTED: { cls: "crit", icon: "✕" },
  ESCALATED: { cls: "warn", icon: "!" },
  INCOMPLETE: { cls: "crit", icon: "!" },
  HEALTHY: { cls: "good", icon: "✓" },
};

export function StatusChip({ status }: { status: string }) {
  const chip = STATUS[status] ?? { cls: "", icon: "…" };
  return <span className={`chip ${chip.cls}`}>{chip.icon} {status.replaceAll("_", " ")}</span>;
}

export function AnomChip({ anomalous }: { anomalous: boolean }) {
  return anomalous
    ? <span className="chip warn">⚠ ANOMALOUS</span>
    : <span className="chip">○ nominal</span>;
}

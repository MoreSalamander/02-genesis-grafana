# System 02: Grafana — Architecture Review V2 (LOCKED)

> **Status: CANONICAL LOCK (V2).** Reviewed decision-by-decision after Parallel was frozen; validated and declared locked in the architecture session; kept as canonical by the user on 2026-08-12 ("keep the architecture plans for parallel and grafana"). Saved verbatim; diagrams in code blocks; the §16 permission table reconstructed from the flattened chat paste. The full reviewed plan is the canonical artifact.

## Architecture Review V2 — Step 2: Grafana

Parallel is frozen. We now move to Grafana — Operational Intelligence without modifying the Parallel architecture. The purpose here is to settle Grafana completely enough that we can lock it before moving to ClickHouse.

### 1. System Identity

**Genesis OS — Operational Intelligence**
Studio function: Operations / Production Infrastructure
Partner: Grafana

Core question:

> "What is happening inside the studio right now, what is going wrong, and what is likely to go wrong next?"

This is not an observability dashboard with an AI assistant attached. The system is an agentic operational cognition layer that continuously interprets the studio's operational state.

### 2. The Core Idea

The Studio Head shouldn't have to inspect: dashboards, logs, traces, alerts, incidents, service health, infrastructure metrics, pipeline failures. Instead:

```
STUDIO HEAD
│
▼
OPERATIONAL COGNITION
│
▼
"What is happening?"
│
┌────────┼────────┐
▼        ▼        ▼
Metrics  Logs   Traces
│        │        │
└────────┼────────┘
         ▼
    CORRELATION
         │
         ▼
     DIAGNOSIS
         │
         ▼
     PREDICTION
         │
         ▼
   RECOMMENDATION
         │
 ┌───────┴───────┐
 ▼               ▼
AUTOMATE      ESCALATE
```

The important transformation is: **Telemetry → operational understanding.**

### 3. Agent Organization

I recommend a hierarchical organization rather than one "Grafana Agent."

```
Operational Executive Agent
│
├── Observability Agent
│   ├── Metrics Analyst
│   ├── Log Analyst
│   └── Trace Analyst
│
├── Correlation Agent
│
├── Incident Diagnosis Agent
│
├── Risk / Prediction Agent
│
├── Remediation Planning Agent
│
└── Operations Decision Agent
```

**Operational Executive Agent** owns the operational objective. It determines: what needs investigation, which operational domain matters, severity, whether multiple signals are related, whether escalation is required, whether remediation should be proposed. It does not directly inspect every telemetry source. It delegates.

### 4. Observability Agents

The Observability Agent decomposes operational reality into three major evidence classes.

- **Metrics Analyst** looks for: CPU, memory, latency, throughput, error rates, queue depth, resource saturation, unusual changes.
- **Log Analyst** looks for: error clusters, recurring failures, exceptions, deployment problems, service failures, anomalous events.
- **Trace Analyst** looks for: request paths, latency propagation, service dependencies, bottlenecks, failed spans, downstream failures.

This is where Grafana becomes structurally indispensable.

### 5. Grafana MCP

The hackathon requirement makes this especially clean. The system must actively use the Grafana Cloud MCP server at runtime. So our operational agents aren't pretending to have observability. They actually query it.

```
Agent
│
▼
Grafana MCP
│
├── Metrics
├── Logs
├── Traces
├── Dashboards
├── Alerts
└── Incidents
```

This gives us an excellent visible demo: "The Studio Head asks what is happening." The system autonomously determines what evidence it needs and queries Grafana.

### 6. Correlation Agent

This is where the system becomes genuinely agentic. Suppose: GPU utilization ↑ + render latency ↑ + queue depth ↑ + worker errors ↑. A dashboard can show those four facts. The Correlation Agent asks: **Are these actually related?**

It builds a hypothesis:

```
Worker resource saturation
↓
Render latency increase
↓
Queue accumulation
↓
Timeouts
↓
Worker errors
```

Then it asks the evidence layer to validate the hypothesis. This gives us: **observation → hypothesis → evidence → validation**, rather than: observation → LLM explanation.

### 7. Diagnosis Agent

Once a correlation exists:

```
Incident
↓
Possible causes
├── Infrastructure saturation
├── Deployment regression
├── Dependency failure
├── Data anomaly
└── External service
```

The Diagnosis Agent evaluates competing hypotheses. Each hypothesis should carry: evidence, supporting signals, contradicting signals, confidence, affected systems, severity, unknowns.

Example:

```
ROOT-CAUSE HYPOTHESIS
Cause: Render worker saturation
Confidence: 87%
Evidence:
• GPU utilization +41%
• queue depth +63%
• render latency +52%
• errors originate from worker pool
Contradicting evidence: None detected
Affected: Render Pipeline
Severity: High
```

That is far more defensible than an LLM simply saying: "It looks like your render workers are overloaded."

### 8. Risk / Prediction Agent

This is the second major differentiator. The system shouldn't only answer "What is broken?" It should answer: **"What is likely to break next?"**

The Prediction Agent examines: historical telemetry, current trends, threshold proximity, incident patterns, resource trajectories, correlated failures.

For the hackathon MVP, I would not attempt a sophisticated ML forecasting system. Instead:

```
Current State + Trend + Historical Pattern + Known Dependency
= Operational Risk Assessment
```

Gemini performs the reasoning. Grafana supplies the evidence. That is enough to demonstrate predictive operational cognition without pretending we've built an industrial forecasting platform.

### 9. Remediation Planning

The system generates a proposed response. For example:

```
RECOMMENDED ACTION
Reduce render concurrency by 20%
and redirect queued jobs to Worker Pool B.

Expected effect:
• Reduce GPU saturation
• Prevent queue overflow
• Lower timeout probability

Risk: Medium
Authorization: Studio Operations approval required
```

Notice the architecture boundary: **Diagnosis does not automatically equal execution.**

### 10. Human Boundary

The Studio Head should see something like:

```
┌──────────────────────────────────────┐
│ OPERATIONAL INCIDENT                 │
│                                      │
│ Render Pipeline Degradation          │
│                                      │
│ Severity: HIGH                       │
│ Confidence: 87%                      │
│                                      │
│ Root Cause                           │
│ Worker pool saturation               │
│                                      │
│ Projected Impact                     │
│ 23 jobs at risk within 18 minutes    │
│                                      │
│ Recommended Action                   │
│ Reduce render concurrency 20%        │
│                                      │
│ [ VIEW EVIDENCE ]                    │
│ [ APPROVE ]  [ REJECT ]              │
└──────────────────────────────────────┘
```

The Studio Head isn't approving an opaque AI action. They're approving a reasoned operational proposal with evidence.

### 11. Context Architecture

This connects directly to the frozen Genesis OS cognition model. Grafana receives inherited context:

```
Studio Context
↓
Operations Context
↓
Production Context
↓
Project Context
↓
Incident Context
```

For example:

```
Studio
└── Production
    └── Film A
        └── Render Pipeline
            └── Incident #482
```

The operational agents don't need the entire studio's context. They receive the smallest relevant context scope. That reduces cognitive noise and improves security.

### 12. Data Flow

```
OPERATIONAL INTENT
│
▼
Operational Executive
│
▼
Context Assembly
│
▼
DataHub Context
│
▼
Investigation Planning
│
┌────────────────┼────────────────┐
▼                ▼                ▼
Metrics         Logs           Traces
│                │                │
└────────────────┼────────────────┘
                 ▼
            Correlation
                 │
                 ▼
             Diagnosis
                 │
                 ▼
             Prediction
                 │
                 ▼
           Recommendation
                 │
                 ▼
        Studio Head Approval
                 │
                 ▼
             Execution
                 │
                 ▼
              Grafana
                 │
                 ▼
             Monitoring
```

### 13. DataHub's Role

We should not turn DataHub into a second Grafana. Their responsibilities remain distinct.

- **Grafana** answers: What is happening operationally?
- **DataHub** answers: What is this thing, what does it relate to, where did it come from, and what context surrounds it?

So: Grafana → Telemetry Evidence → DataHub → Contextual Interpretation.

DataHub can provide relationships such as:

```
Service
↓ belongs to
Production Pipeline
↓ used by
Project
↓ owned by
Department
```

That context makes telemetry meaningful.

### 14. Gemini's Role

Gemini is the cognition layer. It performs: investigation planning, evidence interpretation, hypothesis generation, hypothesis comparison, causal reasoning, risk assessment, recommendation generation, natural-language explanation, structured decision output.

**It should not invent telemetry. Every operational conclusion should trace back to retrieved evidence.**

### 15. Failure Architecture

- **Grafana unavailable:** MCP unavailable → Operational investigation blocked → No fabricated answer → Escalate / retry.
- **Conflicting telemetry:** Metric says healthy + Logs show failures → CONFLICT → Request additional evidence → Lower confidence → Escalate if unresolved.
- **Agents disagree:** Diagnosis A (deployment regression) vs Diagnosis B (infrastructure saturation) → Evidence Review → unresolved conflict → human escalation.
- **Remediation fails:** Action → Verification → Failure → Rollback / escalation → Incident state updated.

**The system should never interpret successful action submission as successful outcome.**

### 16. Security

The operational system gets a strict permission hierarchy:

```
READ TELEMETRY → ANALYZE → RECOMMEND → REQUEST AUTHORIZATION → EXECUTE
```

Different agents receive different permissions:

| Agent | Read | Analyze | Recommend | Execute |
|---|---|---|---|---|
| Metrics Analyst | ✓ | ✓ | | |
| Log Analyst | ✓ | ✓ | | |
| Trace Analyst | ✓ | ✓ | | |
| Correlation | ✓ | ✓ | ✓ | |
| Diagnosis | ✓ | ✓ | ✓ | |
| Prediction | ✓ | ✓ | ✓ | |
| Remediation | ✓ | ✓ | ✓ | restricted |
| Executive | ✓ | ✓ | ✓ | approval only |

This becomes especially important when Genesis OS eventually spans all five systems.

### 17. Demo Scenario

- **Scene 1 — Studio Head:** "How is production doing right now?" The system doesn't just answer from a dashboard. It launches an investigation.
- **Scene 2 — Agent activity:** Show: Operational Executive → Checking production context → Metrics Analyst → Log Analyst → Trace Analyst → Correlation Agent → Diagnosis Agent. This makes the agentic behavior visible.
- **Scene 3 — Discovery:** The system discovers: render latency ↑, queue depth ↑, worker errors ↑, GPU saturation ↑. Then correlates them.
- **Scene 4 — Prediction:** "At the current trajectory, the render queue is likely to exceed capacity within approximately 18 minutes."
- **Scene 5 — Recommendation:**

```
ROOT CAUSE: Worker pool saturation
CONFIDENCE: 87%
RECOMMENDATION: Reduce concurrency 20%
PROJECTED RESULT: Prevent queue overflow
```

- **Scene 6 — Human authorization:** Studio Head clicks APPROVE.
- **Scene 7 — Verification:** The system executes the authorized action. Grafana immediately becomes the feedback mechanism:

```
Before                After
GPU: 94%              GPU: 76%
Queue: 81             Queue: 39
Latency: 8.4s         Latency: 4.7s
```

Then: "Remediation successful."

That is a very strong three-minute demonstration. It visibly demonstrates: **observe → correlate → diagnose → predict → recommend → authorize → act → verify.**

### 18. MVP vs Production

**Hackathon MVP needs:** Google Cloud, Gemini, Grafana Cloud, Grafana MCP, DataHub, representative production telemetry, multi-agent workflow, evidence-linked reasoning, recommendation, human approval, one controlled remediation, post-action verification, polished UI.

**Production Genesis OS eventually adds:** continuous event ingestion, persistent incident state, historical operational memory, automated anomaly detection, dependency graphs, service topology, predictive modeling, automated remediation, rollback, policy engine, approval workflows, multi-studio operations, cross-system reasoning, full audit trail.

We don't need all of that for the submission. But the MVP should be architected so those capabilities have somewhere to go.

### 19. What Makes This Different From Parallel

This distinction needs to stay extremely clean.

- **Parallel** — Outside world. What should we know? External signals → evidence → intelligence → opportunity/threat.
- **Grafana** — Inside operations. What is happening? Telemetry → operational state → diagnosis → predicted risk → intervention.
- **ClickHouse** — Institutional history. What has our accumulated data taught us?
- **IBM** — Executive decision. Given everything we know, what should we do?
- **Replit** — Capability creation. What capability do we need, and can Genesis build it?

That separation is what prevents the five systems from becoming five versions of the same agent.

### 20. Proposed Lock (as locked)

> Genesis OS — Operational Intelligence is the studio's agentic operational cognition subsystem. It uses Grafana's runtime MCP capabilities as its primary telemetry interface, Gemini as its reasoning engine, and Genesis OS contextual knowledge to transform metrics, logs, traces, alerts, and incidents into correlated diagnoses, predictive risk assessments, and evidence-backed operational recommendations. Authorized interventions are executed within explicit permission boundaries and verified through subsequent telemetry.

The defining workflow is:

```
OBSERVE → CORRELATE → DIAGNOSE → PREDICT → RECOMMEND → AUTHORIZE → ACT → VERIFY
```

### Lock record

Validated and declared locked in the architecture session ("System 02: Genesis OS — Operational Intelligence (Grafana) is fully locked and frozen"), with these lock points: system identity & scope (Operational Intelligence, partner Grafana); Operational Executive managing the cognitive sub-agents (Observability Analysts, Correlation, Diagnosis, Risk/Prediction, Remediation Planning); active runtime reliance on the Grafana MCP server as the primary telemetry substrate; strictly downward-flowing scoped context (Studio→Operations→Production→Project→Incident); structured diagnosis objects (root-cause hypotheses, confidence, supporting/contradicting signals, affected pipelines, severity); explicit failure modes with zero hallucinated telemetry; human-in-the-loop for all consequential remediation; and the OBSERVE→…→VERIFY loop. Kept as canonical by the user on 2026-08-12.


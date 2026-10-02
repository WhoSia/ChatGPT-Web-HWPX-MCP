export type StaticVerdict = "PASS" | "PASS_WITH_WARNINGS" | "NEEDS_REPAIR";
export type RenderRequirement = "REQUIRED" | "WHEN_AVAILABLE" | "NOT_REQUIRED";
export type RenderVerdict = "NOT_PROVIDED" | "PENDING" | "PASS" | "PASS_WITH_WARNINGS" | "NEEDS_REPAIR" | "INVALID";
export type HumanRequirement = "REQUIRED" | "NOT_REQUIRED";
export type HumanVerdict = "PENDING" | "PASS" | "FAIL";
export type NextAction = "REPAIR" | "WAIT_RENDER" | "WAIT_HUMAN" | "DELIVER" | "HOLD";

export interface GateSnapshot {
  static_verdict: StaticVerdict;
  render_requirement: RenderRequirement;
  render_verdict: RenderVerdict;
  repairable: boolean;
  repairs_used: number;
  max_repairs: number;
  policy_ok: boolean;
  footprint_ok: boolean;
  human_requirement: HumanRequirement;
  human_verdict: HumanVerdict;
}

export interface GateDecision {
  action: NextAction;
  reason: string;
}

export function decideNext(s: GateSnapshot): GateDecision {
  if (!s.policy_ok) return {action:"HOLD", reason:"POLICY_GATE_FAILED"};
  if (!s.footprint_ok) return {action:"HOLD", reason:"PRESERVATION_GATE_FAILED"};
  if (s.static_verdict === "NEEDS_REPAIR") {
    if (s.repairs_used >= s.max_repairs) return {action:"HOLD", reason:"REPAIR_LIMIT_EXHAUSTED"};
    if (!s.repairable) return {action:"HOLD", reason:"STATIC_REPAIR_GAP"};
    return {action:"REPAIR", reason:"STATIC_REPAIR_REQUIRED"};
  }

  const renderProvided = !["NOT_PROVIDED","PENDING"].includes(s.render_verdict);
  if (s.render_requirement === "REQUIRED") {
    if (!renderProvided) return {action:"WAIT_RENDER", reason:"RENDER_EVIDENCE_REQUIRED"};
    if (s.render_verdict === "INVALID") return {action:"HOLD", reason:"RENDER_EVIDENCE_INVALID"};
    if (s.render_verdict === "NEEDS_REPAIR") {
      if (s.repairs_used >= s.max_repairs) return {action:"HOLD", reason:"REPAIR_LIMIT_EXHAUSTED"};
      if (!s.repairable) return {action:"HOLD", reason:"RENDER_REPAIR_GAP"};
      return {action:"REPAIR", reason:"RENDER_REPAIR_REQUIRED"};
    }
  } else if (s.render_requirement === "WHEN_AVAILABLE" && renderProvided) {
    if (s.render_verdict === "INVALID") return {action:"HOLD", reason:"RENDER_EVIDENCE_INVALID"};
    if (s.render_verdict === "NEEDS_REPAIR") {
      if (s.repairs_used >= s.max_repairs) return {action:"HOLD", reason:"REPAIR_LIMIT_EXHAUSTED"};
      if (!s.repairable) return {action:"HOLD", reason:"RENDER_REPAIR_GAP"};
      return {action:"REPAIR", reason:"RENDER_REPAIR_REQUIRED"};
    }
  }

  if (s.human_requirement === "REQUIRED") {
    if (s.human_verdict === "PENDING") return {action:"WAIT_HUMAN", reason:"HUMAN_REVIEW_REQUIRED"};
    if (s.human_verdict === "FAIL") return {action:"HOLD", reason:"HUMAN_REVIEW_FAILED"};
  }
  return {action:"DELIVER", reason:"ALL_REQUIRED_GATES_PASS"};
}

export const P344_RUNTIME_CONTRACT = {
  schema: "chatgpt-web-hwpx-mcp/p3.44/orchestrator-runtime/v1",
  phase: "P3.44",
  language_authority: {
    runtime_gate: "RUST_PRODUCTION_BINARY",
    independent_orchestrator: "TYPESCRIPT",
    native_hwpx_adapter: "PYTHON",
    hancom_world_contact: "POWERSHELL_WINDOWS"
  },
  bounded_repair_rounds: {minimum:0, maximum:3, default:2},
  terminal_actions: ["DELIVER","HOLD"],
  external_evidence_pauses: ["WAIT_RENDER","WAIT_HUMAN"]
} as const;

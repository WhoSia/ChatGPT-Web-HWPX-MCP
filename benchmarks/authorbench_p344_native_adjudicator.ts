import * as fs from "fs";

export interface NativeBlindCase {
  case_id: string;
  source_sha256: string;
  renderer: {
    hancom_native: boolean;
    version: string;
    executable_sha256: string;
    dpi: number;
  };
  page_count: number;
  world_contact_valid: boolean;
  diagnostic_verdict: string;
  severity_counts: Record<string, number>;
  finding_codes: string[];
  render_receipt_sha256: string;
}

export interface NativeBlindPacket {
  schema: string;
  phase: "P3.44";
  cases: NativeBlindCase[];
}

export function scoreNativeBlindPacket(packet: NativeBlindPacket) {
  const forbidden = ["domain", "split", "audience", "generation_notes", "title", "body1", "body2"];
  if (!packet || packet.phase !== "P3.44" || !Array.isArray(packet.cases)) {
    throw new Error("invalid P3.44 native blind packet");
  }
  const seen = new Set<string>();
  const scores = packet.cases.map((row) => {
    const raw = JSON.stringify(row);
    for (const key of forbidden) {
      if (raw.includes('"' + key + '"')) throw new Error("native blind packet leaked " + key);
    }
    if (!row.case_id || seen.has(row.case_id)) throw new Error("duplicate/empty native case id");
    seen.add(row.case_id);
    const critical = Number(row.severity_counts?.CRITICAL || 0);
    const high = Number(row.severity_counts?.HIGH || 0);
    const receiptHashOk = /^[0-9a-f]{64}$/i.test(row.render_receipt_sha256 || "");
    const sourceHashOk = /^[0-9a-f]{64}$/i.test(row.source_sha256 || "");
    const exeHashOk = /^[0-9a-f]{64}$/i.test(row.renderer?.executable_sha256 || "");
    const verdictOk = ["PASS", "PASS_WITH_WARNINGS"].includes(String(row.diagnostic_verdict || ""));
    const pass =
      row.renderer?.hancom_native === true &&
      Boolean(String(row.renderer?.version || "").trim()) &&
      exeHashOk &&
      Number(row.renderer?.dpi || 0) > 0 &&
      row.world_contact_valid === true &&
      Number(row.page_count || 0) > 0 &&
      verdictOk &&
      critical === 0 &&
      high === 0 &&
      receiptHashOk &&
      sourceHashOk;
    return {
      case_id: row.case_id,
      native_render_pass: pass,
      diagnostic_verdict: row.diagnostic_verdict,
      page_count: row.page_count,
      high_or_critical_findings: high + critical,
      evidence: pass ? "HANCOM_NATIVE_RENDER_EVIDENCE" : "NATIVE_RENDER_GATE_FAILED"
    };
  });
  return {
    schema: "authorbench/p3.44/native-blind-scores/v1",
    case_count: scores.length,
    scores,
    authority: "NATIVE_RENDER_SCORING_BLIND_TO_DOMAIN_SPLIT_AUDIENCE"
  };
}

export function adjudicateNativePromotion(manifest: any, scored: any, staticEvaluation?: any) {
  const byId = new Map<string, any>((scored.scores || []).map((x: any) => [x.case_id, x]));
  const holdout = (manifest.cases || []).filter((x: any) => x.split === "HOLDOUT");
  const rows = holdout.map((x: any) => ({manifest: x, score: byId.get(x.case_id)}));
  const missing = rows.filter((x: any) => !x.score).map((x: any) => x.manifest.case_id);
  const failures = rows.filter((x: any) => x.score && !x.score.native_render_pass).map((x: any) => x.manifest.case_id);
  const domains = new Set(rows.map((x: any) => x.manifest.domain));
  const expectedHoldout = Number(manifest.promotion?.holdout_cases || 0);
  const requiredDomains = Number(manifest.promotion?.required_holdout_domains || 0);
  const staticPromotion = staticEvaluation?.promotion?.static_promotion || "NOT_SUPPLIED";
  const nativePromotion =
    holdout.length === expectedHoldout &&
    domains.size >= requiredDomains &&
    missing.length === 0 &&
    failures.length === 0
      ? "PASS"
      : "FAIL";
  return {
    schema: "authorbench/p3.44/native-promotion/v1",
    holdout_count: holdout.length,
    holdout_domain_count: domains.size,
    missing_cases: missing,
    native_failures: failures,
    static_promotion: staticPromotion,
    native_render_promotion: nativePromotion,
    human_visual_promotion: "WITHHELD",
    closure_candidate: staticPromotion === "PASS" && nativePromotion === "PASS",
    authority: "BLIND_NATIVE_SCORING_SEPARATE_FROM_SPLIT_AWARE_PROMOTION_AND_HUMAN_VISUAL_REVIEW"
  };
}

if (require.main === module) {
  const [, , blindPath, manifestPath, staticPath, outputPath] = process.argv;
  if (!blindPath || !manifestPath || !staticPath || !outputPath) {
    throw new Error("usage: native_adjudicator BLIND_JSON FROZEN_MANIFEST STATIC_EVALUATION OUTPUT_JSON");
  }
  const blind = JSON.parse(fs.readFileSync(blindPath, "utf8"));
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  const staticEvaluation = JSON.parse(fs.readFileSync(staticPath, "utf8"));
  const scored = scoreNativeBlindPacket(blind);
  const promotion = adjudicateNativePromotion(manifest, scored, staticEvaluation);
  fs.writeFileSync(outputPath, JSON.stringify({scored, promotion}, null, 2) + "\n", "utf8");
  process.stdout.write(JSON.stringify(promotion) + "\n");
  if (!promotion.closure_candidate) process.exitCode = 2;
}

import { decideNext, GateSnapshot } from "../contracts/p344_orchestrator";

export interface BlindCase {
  case_id: string;
  artifact_sha256: string;
  final_static: {
    verdict: "PASS" | "PASS_WITH_WARNINGS" | "NEEDS_REPAIR";
    severity_counts: Record<string, number>;
    finding_codes: string[];
  };
  repairs: Array<{preservation_passed:boolean; preservation_grade:string}>;
  gate_snapshot: GateSnapshot;
}

export function scoreBlindPacket(packet: {cases: BlindCase[]}){
  const forbidden=["domain","split","audience","generation_notes"];
  const scores=packet.cases.map((row)=>{
    const raw=JSON.stringify(row);
    for(const key of forbidden){
      if(raw.includes('"'+key+'"')) throw new Error("blind packet leaked "+key);
    }
    const high=(row.final_static.severity_counts.HIGH||0)+(row.final_static.severity_counts.CRITICAL||0);
    const repairsOk=row.repairs.every(r=>r.preservation_passed && ["TARGETED_PARTS_ONLY","PACKAGE_IDENTICAL"].includes(r.preservation_grade));
    const decision=decideNext(row.gate_snapshot);
    const staticPass=["PASS","PASS_WITH_WARNINGS"].includes(row.final_static.verdict) && high===0 && repairsOk;
    return {
      case_id:row.case_id,
      static_pass:staticPass,
      next_action:decision.action,
      gate_reason:decision.reason,
      render_status:decision.action==="WAIT_RENDER" ? "WITHHELD" : decision.action==="DELIVER" ? "NOT_REQUIRED" : "BLOCKED"
    };
  });
  return {schema:"authorbench/p3.44/blind-scores/v1",scores};
}

export function adjudicatePromotion(manifest:any, scored:any){
  const byId=new Map(scored.scores.map((x:any)=>[x.case_id,x]));
  const holdout=manifest.cases.filter((x:any)=>x.split==="HOLDOUT");
  const rows=holdout.map((x:any)=>({manifest:x,score:byId.get(x.case_id)}));
  const missing=rows.filter((x:any)=>!x.score).map((x:any)=>x.manifest.case_id);
  const staticFailures=rows.filter((x:any)=>x.score && !x.score.static_pass).map((x:any)=>x.manifest.case_id);
  const domains=new Set(rows.map((x:any)=>x.manifest.domain));
  const staticPromotion = missing.length || staticFailures.length || domains.size < manifest.promotion.required_holdout_domains ? "FAIL" : "PASS";
  const renderPromotion = rows.every((x:any)=>x.score && x.score.render_status==="PASS") ? "PASS" : "WITHHELD";
  return {
    schema:"authorbench/p3.44/promotion/v1",
    holdout_count:holdout.length,
    holdout_domain_count:domains.size,
    missing_cases:missing,
    static_failures:staticFailures,
    static_promotion:staticPromotion,
    render_promotion:renderPromotion,
    authority:"BLIND_STATIC_SCORING_SEPARATE_FROM_HOLDOUT_PROMOTION_AND_NATIVE_RENDER"
  };
}

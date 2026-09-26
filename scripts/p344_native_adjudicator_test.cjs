const { scoreNativeBlindPacket, adjudicateNativePromotion } = require("../.tmp/p344-ts/benchmarks/authorbench_p344_native_adjudicator.js");

function row(id){
  return {
    case_id:id,
    source_sha256:"a".repeat(64),
    renderer:{hancom_native:true,version:"13.0.0.3622",executable_sha256:"b".repeat(64),dpi:144},
    page_count:2,
    world_contact_valid:true,
    diagnostic_verdict:"PASS_WITH_WARNINGS",
    severity_counts:{CRITICAL:0,HIGH:0,MEDIUM:1,LOW:1,INFO:0},
    finding_codes:["LOW_SIGNAL"],
    render_receipt_sha256:"c".repeat(64)
  };
}
const blind={schema:"authorbench/p3.44/native-blind-packet/v1",phase:"P3.44",cases:["AB44-05","AB44-06","AB44-07","AB44-08"].map(row)};
const manifest={promotion:{holdout_cases:4,required_holdout_domains:4},cases:[
  {case_id:"AB44-05",split:"HOLDOUT",domain:"A"},
  {case_id:"AB44-06",split:"HOLDOUT",domain:"B"},
  {case_id:"AB44-07",split:"HOLDOUT",domain:"C"},
  {case_id:"AB44-08",split:"HOLDOUT",domain:"D"},
]};
const staticEvaluation={promotion:{static_promotion:"PASS"}};
let scored=scoreNativeBlindPacket(blind);
let promo=adjudicateNativePromotion(manifest,scored,staticEvaluation);
if(!promo.closure_candidate || promo.native_render_promotion!=="PASS") throw new Error("expected native PASS");
const bad=JSON.parse(JSON.stringify(blind));
bad.cases[2].severity_counts.HIGH=1;
scored=scoreNativeBlindPacket(bad);
promo=adjudicateNativePromotion(manifest,scored,staticEvaluation);
if(promo.native_render_promotion!=="FAIL") throw new Error("expected native FAIL");
let leaked=false;
try{
  const leak=JSON.parse(JSON.stringify(blind));
  leak.cases[0].split="HOLDOUT";
  scoreNativeBlindPacket(leak);
}catch(e){ leaked=true; }
if(!leaked) throw new Error("blind leakage was not rejected");
console.log(JSON.stringify({status:"PASS",runtime:"typescript",native_cases:4}));

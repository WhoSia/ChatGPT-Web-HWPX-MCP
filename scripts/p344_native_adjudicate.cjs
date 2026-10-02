const fs=require("fs");
const {scoreNativeBlindPacket,adjudicateNativePromotion}=require("../.tmp/p344-ts/benchmarks/authorbench_p344_native_adjudicator.js");
const [, , blindPath, manifestPath, staticPath, outputPath]=process.argv;
if(!blindPath||!manifestPath||!staticPath||!outputPath){
  throw new Error("usage: p344_native_adjudicate BLIND_JSON FROZEN_MANIFEST STATIC_EVALUATION OUTPUT_JSON");
}
const blind=JSON.parse(fs.readFileSync(blindPath,"utf8"));
const manifest=JSON.parse(fs.readFileSync(manifestPath,"utf8"));
const staticEvaluation=JSON.parse(fs.readFileSync(staticPath,"utf8"));
const scored=scoreNativeBlindPacket(blind);
const promotion=adjudicateNativePromotion(manifest,scored,staticEvaluation);
fs.writeFileSync(outputPath,JSON.stringify({scored,promotion},null,2)+"\n","utf8");
process.stdout.write(JSON.stringify(promotion)+"\n");
if(!promotion.closure_candidate) process.exitCode=2;

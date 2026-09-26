const fs=require("fs");
const path=require("path");
const {decideNext}=require("../.tmp/p344-ts/contracts/p344_orchestrator.js");
const rows=fs.readFileSync(path.join(__dirname,"..","benchmarks","p344_gate_golden.tsv"),"utf8").trim().split(/\r?\n/).slice(1);
let checked=0;
for(const line of rows){
  const c=line.split("\t");
  const d=decideNext({
    static_verdict:c[1],render_requirement:c[2],render_verdict:c[3],
    repairable:c[4]==="true",repairs_used:Number(c[5]),max_repairs:Number(c[6]),
    policy_ok:c[7]==="true",footprint_ok:c[8]==="true",
    human_requirement:c[9],human_verdict:c[10]
  });
  if(d.action!==c[11]||d.reason!==c[12]) throw new Error(c[0]+": "+JSON.stringify(d));
  checked++;
}
console.log(JSON.stringify({status:"PASS",runtime:"typescript",fixtures:checked}));

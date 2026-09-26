const fs=require("fs"),path=require("path");const {adjudicatePolicyGate}=require("../.tmp/p343-ts/p343_policy.js");
const rows=fs.readFileSync(path.join(__dirname,"..","benchmarks","p343_policy_gate_golden.tsv"),"utf8").trim().split(/\r?\n/).slice(1);
for(const line of rows){const [name,hard,sem,str,grade,expected]=line.split("\t");const actual=adjudicatePolicyGate(Number(hard),sem==="true",str==="true",grade);if(actual!==expected)throw new Error(name+":"+actual+"!="+expected);}
console.log(JSON.stringify({status:"PASS",runtime:"typescript",fixture_count:rows.length}));

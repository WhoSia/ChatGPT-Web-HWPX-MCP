const cp=require("child_process");
const path=require("path");
const root=path.resolve(__dirname,"..");
const cli=path.join(root,".tmp","p346-ts","scripts","p346_platform_cli.js");
const guard=process.env.P346_GUARD_BIN||path.join(root,"rust","p346_guard","target","release","p346-guard");

function run(bin,args,input){
  const p=cp.spawnSync(bin,args,{input:JSON.stringify(input||{}),encoding:"utf8"});
  if(p.status!==0)throw new Error((p.stderr||p.stdout||"command failed").trim());
  return JSON.parse(p.stdout);
}
const plan={
  schema:"chatgpt-web-hwpx-mcp/p3.46/effect-plan/v1",
  nodes:[
    {id:"a",deps:[],effect:"READ_ONLY",action:"REUSE",reusable:true},
    {id:"b",deps:["a"],effect:"DOCUMENT_MUTATION",action:"EXECUTE"},
    {id:"c",deps:["b"],effect:"EXTERNAL_WORLD_CONTACT",action:"WAIT_EXTERNAL"},
    {id:"d",deps:["c"],effect:"DELIVERY",action:"EXECUTE"},
  ],
};
const ts=run(process.execPath,[cli,"validate-composition"],plan);
const rs=run(guard,["check-plan"],plan);
if(JSON.stringify(ts.topological_order)!==JSON.stringify(rs.topological_order)){
  throw new Error("TypeScript/Rust topological order mismatch");
}

let rejected=0;
const negatives=[
  {schema:plan.schema,nodes:[
    {id:"delivery",effect:"DELIVERY"},
    {id:"late",deps:["delivery"],effect:"PURE"},
  ]},
  {schema:plan.schema,nodes:[
    {id:"mutation",effect:"DOCUMENT_MUTATION",action:"REUSE",reusable:true},
  ]},
];
for(const bad of negatives){
  try{run(process.execPath,[cli,"validate-composition"],bad);}catch(_){rejected++;}
  try{run(guard,["check-plan"],bad);}catch(_){rejected++;}
}
if(rejected!==4)throw new Error("cross-runtime negative controls did not all reject");

const configPlan={
  schema:plan.schema,
  nodes:[
    {id:"inspect",effect:"READ_ONLY"},
    {id:"config",deps:["inspect"],effect:"RUNTIME_CONFIGURATION"},
    {id:"deliver",deps:["config"],effect:"DELIVERY"},
  ],
};
const configTs=run(process.execPath,[cli,"validate-composition"],configPlan);
const configRs=run(guard,["check-plan"],configPlan);
if(JSON.stringify(configTs.topological_order)!==JSON.stringify(configRs.topological_order)){
  throw new Error("runtime-configuration effect parity failed");
}
console.log(JSON.stringify({
  ok:true,
  valid_nodes:4,
  negative_rejections:rejected,
  runtime_configuration_parity:true,
  authority:"P346_CROSS_RUNTIME_EFFECT_PARITY_PASS",
}));

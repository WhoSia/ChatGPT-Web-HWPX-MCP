declare function require(name:string):any;
declare const Buffer:any;
const crypto=require("crypto");

export type Effect="READ_ONLY"|"PURE"|"DOCUMENT_MUTATION"|"RUNTIME_CONFIGURATION"|"EXTERNAL_WORLD_CONTACT"|"DELIVERY";
export type EffectAction="EXECUTE"|"REUSE"|"WAIT_EXTERNAL";

export interface CapabilitySpec {
  name:string; version:string; effect:Effect; adapter:string;
  deterministic:boolean; evidence:string[];
}
export interface NodeSpec {
  kind:string; capability:string; effect:Effect; adapter:string; reusable:boolean;
}
export interface ToolSpec {
  name:string; capability:string; effect:Effect; description:string; input_schema:any;
}
export interface ExtensionManifest {
  schema:"chatgpt-web-hwpx-mcp/p3.46/extension-manifest/v1";
  extension_id:string; version:string; host_abi:"p3.46-extension-v1";
  execution:{
    mode:"WASM_NO_IMPORTS"; module_sha256:string; entrypoint:"p346_run";
    deterministic:true; max_module_bytes:number; timeout_ms:number;
  };
  capabilities:CapabilitySpec[]; node_kinds:NodeSpec[]; tools?:ToolSpec[];
}

const EFFECTS:Effect[]=["READ_ONLY","PURE","DOCUMENT_MUTATION","RUNTIME_CONFIGURATION","EXTERNAL_WORLD_CONTACT","DELIVERY"];
const EFFECT_SET=new Set<string>(EFFECTS);

function assertId(v:string,label:string){
  if(!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(String(v||""))) throw new Error("invalid "+label);
}
function assertVersion(v:string,label:string){
  if(!/^\d+(\.\d+){0,2}$/.test(String(v||""))) throw new Error("invalid "+label);
}
function assertDeterministic(v:any,path="$"):void{
  if(v===null||typeof v==="string"||typeof v==="boolean") return;
  if(typeof v==="number"){
    if(!Number.isSafeInteger(v)) throw new Error("deterministic payload requires safe integers at "+path);
    return;
  }
  if(Array.isArray(v)){v.forEach((x,i)=>assertDeterministic(x,path+"["+i+"]"));return;}
  if(typeof v==="object"){
    for(const k of Object.keys(v)){
      if(v[k]===undefined) throw new Error("undefined is not deterministic at "+path+"."+k);
      assertDeterministic(v[k],path+"."+k);
    }
    return;
  }
  throw new Error("unsupported deterministic value at "+path);
}
export function canonicalJson(v:any):string{
  assertDeterministic(v);
  if(v===null) return "null";
  if(typeof v==="string"||typeof v==="boolean"||typeof v==="number") return JSON.stringify(v);
  if(Array.isArray(v)) return "["+v.map(canonicalJson).join(",")+"]";
  const keys=Object.keys(v).sort();
  return "{"+keys.map(k=>JSON.stringify(k)+":"+canonicalJson(v[k])).join(",")+"}";
}
export function sha256(v:any):string{
  return crypto.createHash("sha256").update(canonicalJson(v),"utf8").digest("hex");
}
function shaBytes(v:any):string{
  return crypto.createHash("sha256").update(v).digest("hex");
}
function readVarUint32(bytes:any,start:number):{value:number;next:number}{
  let value=0,shift=0,index=start;
  for(let i=0;i<5;i++){
    if(index>=bytes.length) throw new Error("truncated WASM varuint32");
    const b=Number(bytes[index++]);
    value|=(b&0x7f)<<shift;
    if((b&0x80)===0) return {value:value>>>0,next:index};
    shift+=7;
  }
  throw new Error("invalid WASM varuint32");
}
function wasmSectionIds(bytes:any):number[]{
  if(bytes.length<8||bytes[0]!==0x00||bytes[1]!==0x61||bytes[2]!==0x73||bytes[3]!==0x6d||
     bytes[4]!==0x01||bytes[5]!==0x00||bytes[6]!==0x00||bytes[7]!==0x00){
    throw new Error("invalid WASM header/version");
  }
  const ids:number[]=[];let offset=8;
  while(offset<bytes.length){
    const id=Number(bytes[offset++]);
    const size=readVarUint32(bytes,offset);offset=size.next;
    if(size.value>bytes.length-offset) throw new Error("truncated WASM section");
    ids.push(id);offset+=size.value;
  }
  return ids;
}
function assertScalarWasmResourceShape(bytes:any):void{
  const ids=wasmSectionIds(bytes);
  const forbidden=new Set([4,5,9,11,12]);
  if(ids.some(id=>forbidden.has(id))){
    throw new Error("sandbox denies WASM table/memory/element/data sections");
  }
}
function annotations(effect:Effect){
  return {
    readOnlyHint:effect==="READ_ONLY"||effect==="PURE",
    destructiveHint:effect==="DOCUMENT_MUTATION"||effect==="RUNTIME_CONFIGURATION",
    openWorldHint:effect==="EXTERNAL_WORLD_CONTACT"||effect==="DELIVERY",
    p346_effect:effect,
  };
}

export const BUILTIN_CAPABILITIES:CapabilitySpec[]=[
  {name:"document.inspect",version:"1.1.0",effect:"READ_ONLY",adapter:"DOCUMENT_SNAPSHOT",deterministic:true,evidence:["STRUCTURAL_NATIVE_FACT"]},
  {name:"document.text.edit",version:"1.1.0",effect:"DOCUMENT_MUTATION",adapter:"DOCUMENT_TEXT_EDIT",deterministic:true,evidence:["REVISION_CAS","PACKAGE_VALIDATION"]},
  {name:"document.format.edit",version:"1.1.0",effect:"DOCUMENT_MUTATION",adapter:"DOCUMENT_FORMAT_EDIT",deterministic:true,evidence:["REVISION_CAS","PACKAGE_VALIDATION"]},
  {name:"document.design.repair",version:"1.1.0",effect:"DOCUMENT_MUTATION",adapter:"DOCUMENT_DESIGN_REPAIR",deterministic:true,evidence:["P3.42_MUTATION_FOOTPRINT","P3.43_POLICY_COMPATIBLE"]},
  {name:"document.render.evidence",version:"1.1.0",effect:"EXTERNAL_WORLD_CONTACT",adapter:"EXTERNAL_RENDER",deterministic:false,evidence:["EXTERNAL_WORLD_CONTACT"]},
  {name:"document.delivery",version:"1.0.0",effect:"DELIVERY",adapter:"DOCUMENT_DELIVERY",deterministic:false,evidence:["SIGNED_DELIVERY_RECEIPT"]},
  {name:"platform.inspect",version:"1.0.0",effect:"READ_ONLY",adapter:"P346_INSPECTOR",deterministic:true,evidence:["REPLAY_VERIFIED_STATE"]},
  {name:"platform.codegen",version:"1.0.0",effect:"PURE",adapter:"P346_CODEGEN",deterministic:true,evidence:["CONTRACT_SHA256"]},
  {name:"platform.configure",version:"1.0.0",effect:"RUNTIME_CONFIGURATION",adapter:"P346_ADAPTER_REGISTRY",deterministic:true,evidence:["GENERATION_CAS","ROLLBACK_RECEIPT","OWNER_SCOPED_DOCUMENT"]},
];

export const BUILTIN_NODES:NodeSpec[]=[
  {kind:"document.snapshot",capability:"document.inspect",effect:"READ_ONLY",adapter:"DOCUMENT_SNAPSHOT",reusable:true},
  {kind:"document.text.edit",capability:"document.text.edit",effect:"DOCUMENT_MUTATION",adapter:"DOCUMENT_TEXT_EDIT",reusable:false},
  {kind:"document.format.edit",capability:"document.format.edit",effect:"DOCUMENT_MUTATION",adapter:"DOCUMENT_FORMAT_EDIT",reusable:false},
  {kind:"document.design.repair",capability:"document.design.repair",effect:"DOCUMENT_MUTATION",adapter:"DOCUMENT_DESIGN_REPAIR",reusable:false},
  {kind:"document.render.evidence",capability:"document.render.evidence",effect:"EXTERNAL_WORLD_CONTACT",adapter:"EXTERNAL_RENDER",reusable:false},
];

export const BUILTIN_TOOLS:ToolSpec[]=[
  {name:"get_developer_platform_contract",capability:"platform.inspect",effect:"READ_ONLY",description:"Return the P3.46 developer-platform constitution.",input_schema:{type:"object",properties:{},additionalProperties:false}},
  {name:"project_document_tool_surface",capability:"platform.codegen",effect:"PURE",description:"Project effect-annotated tools from capability contracts.",input_schema:{type:"object",properties:{extensions:{type:"array"}},additionalProperties:false}},
  {name:"validate_document_effect_composition",capability:"platform.codegen",effect:"PURE",description:"Reject illegal effect DAGs before execution.",input_schema:{type:"object",required:["plan"],properties:{plan:{type:"object"}},additionalProperties:false}},
  {name:"validate_document_tool_sequence",capability:"platform.codegen",effect:"PURE",description:"Reject illegal tool-effect sequences before execution.",input_schema:{type:"object",required:["effects"],properties:{effects:{type:"array",items:{type:"string"}}},additionalProperties:false}},
  {name:"validate_projected_document_tool_plan",capability:"platform.codegen",effect:"PURE",description:"Derive effects from projected tool contracts and reject illegal DAG composition or caller effect overrides.",input_schema:{type:"object",required:["plan"],properties:{plan:{type:"object"},extensions:{type:"array"}},additionalProperties:false}},
  {name:"validate_projected_document_tool_sequence",capability:"platform.codegen",effect:"PURE",description:"Derive effects from projected tool contracts and validate a tool-name sequence.",input_schema:{type:"object",required:["tool_names"],properties:{tool_names:{type:"array",items:{type:"string"}},extensions:{type:"array"}},additionalProperties:false}},
  {name:"inspect_document_runtime",capability:"platform.inspect",effect:"READ_ONLY",description:"Inspect a replay-verified transaction DAG and event chain.",input_schema:{type:"object",required:["document_id","run_id"],properties:{document_id:{type:"string"},run_id:{type:"string"}},additionalProperties:false}},
  {name:"get_document_runtime_diagnostics",capability:"platform.inspect",effect:"READ_ONLY",description:"Return structured diagnostics without mutating runtime state.",input_schema:{type:"object",required:["document_id","run_id"],properties:{document_id:{type:"string"},run_id:{type:"string"}},additionalProperties:false}},
  {name:"get_host_adapter_registry",capability:"platform.inspect",effect:"READ_ONLY",description:"Inspect admitted host-adapter profiles or one owned document selection.",input_schema:{type:"object",properties:{document_id:{type:"string"}},additionalProperties:false}},
  {name:"hot_swap_document_host_adapter_profile",capability:"platform.configure",effect:"RUNTIME_CONFIGURATION",description:"CAS-switch one owned document to a pre-admitted host-adapter profile.",input_schema:{type:"object",required:["document_id","target_profile","expected_generation"],properties:{document_id:{type:"string"},target_profile:{type:"string"},expected_generation:{type:"integer"}},additionalProperties:false}},
  {name:"rollback_document_host_adapter_profile",capability:"platform.configure",effect:"RUNTIME_CONFIGURATION",description:"Rollback one owned document host-adapter profile under generation CAS.",input_schema:{type:"object",required:["document_id","expected_generation"],properties:{document_id:{type:"string"},expected_generation:{type:"integer"}},additionalProperties:false}},
  {name:"validate_sandboxed_document_extension",capability:"platform.codegen",effect:"PURE",description:"Validate one deterministic no-import WASM extension.",input_schema:{type:"object",required:["manifest"],properties:{manifest:{type:"object"}},additionalProperties:false}},
  {name:"execute_sandboxed_document_extension_probe",capability:"platform.codegen",effect:"PURE",description:"Execute one bounded pure WASM extension probe.",input_schema:{type:"object",required:["manifest","module_base64"],properties:{manifest:{type:"object"},module_base64:{type:"string"}},additionalProperties:false}},
  {name:"generate_document_platform_contracts",capability:"platform.codegen",effect:"PURE",description:"Generate canonical effect/capability/node/tool contracts.",input_schema:{type:"object",properties:{extensions:{type:"array"}},additionalProperties:false}},
];

function normCapability(raw:any):CapabilitySpec{
  if(!raw||typeof raw!=="object") throw new Error("capability must be object");
  assertId(String(raw.name||""),"capability name"); assertVersion(String(raw.version||""),"capability version");
  const effect=String(raw.effect||"") as Effect; if(!EFFECT_SET.has(effect)) throw new Error("invalid capability effect");
  assertId(String(raw.adapter||""),"capability adapter");
  if(!Array.isArray(raw.evidence)||raw.evidence.some((x:any)=>typeof x!=="string"||!x.trim())) throw new Error("invalid capability evidence");
  return {name:String(raw.name),version:String(raw.version),effect,adapter:String(raw.adapter),deterministic:Boolean(raw.deterministic),evidence:[...new Set<string>(raw.evidence.map(String))].sort()};
}
function normNode(raw:any):NodeSpec{
  if(!raw||typeof raw!=="object") throw new Error("node must be object");
  assertId(String(raw.kind||""),"node kind"); assertId(String(raw.capability||""),"node capability"); assertId(String(raw.adapter||""),"node adapter");
  const effect=String(raw.effect||"") as Effect; if(!EFFECT_SET.has(effect)) throw new Error("invalid node effect");
  const reusable=Boolean(raw.reusable);
  if(reusable&&!["READ_ONLY","PURE"].includes(effect)) throw new Error("only READ_ONLY/PURE nodes may be reusable");
  return {kind:String(raw.kind),capability:String(raw.capability),effect,adapter:String(raw.adapter),reusable};
}
function normTool(raw:any):ToolSpec{
  if(!raw||typeof raw!=="object") throw new Error("tool must be object");
  assertId(String(raw.name||""),"tool name"); assertId(String(raw.capability||""),"tool capability");
  const effect=String(raw.effect||"") as Effect; if(!EFFECT_SET.has(effect)) throw new Error("invalid tool effect");
  const schema=raw.input_schema||{type:"object",properties:{},additionalProperties:false};
  if(schema.type!=="object") throw new Error("tool input schema must be object");
  return {name:String(raw.name),capability:String(raw.capability),effect,description:String(raw.description||""),input_schema:JSON.parse(JSON.stringify(schema))};
}

export function validateExtensionManifest(raw:any):ExtensionManifest&{manifest_sha256:string}{
  if(!raw||raw.schema!=="chatgpt-web-hwpx-mcp/p3.46/extension-manifest/v1"||raw.host_abi!=="p3.46-extension-v1") throw new Error("invalid P3.46 extension manifest");
  assertId(String(raw.extension_id||""),"extension_id"); assertVersion(String(raw.version||""),"extension version");
  const ex=raw.execution||{};
  if(ex.mode!=="WASM_NO_IMPORTS"||ex.entrypoint!=="p346_run"||ex.deterministic!==true) throw new Error("executable extensions require deterministic WASM_NO_IMPORTS p346_run ABI");
  if(!/^[0-9a-f]{64}$/.test(String(ex.module_sha256||""))) throw new Error("invalid module_sha256");
  const maxBytes=Number(ex.max_module_bytes), timeout=Number(ex.timeout_ms);
  if(!Number.isInteger(maxBytes)||maxBytes<8||maxBytes>65536) throw new Error("max_module_bytes must be 8..65536");
  if(!Number.isInteger(timeout)||timeout<25||timeout>1500) throw new Error("timeout_ms must be 25..1500");
  const caps=(raw.capabilities||[]).map(normCapability) as CapabilitySpec[];
  const nodes=(raw.node_kinds||[]).map(normNode) as NodeSpec[];
  const tools=(raw.tools||[]).map(normTool) as ToolSpec[];
  if(caps.length<1||caps.length>32||nodes.length>32||tools.length>32) throw new Error("extension inventory bound violated");
  const capNames=new Set(caps.map(x=>x.name));
  const capBy=new Map(caps.map(x=>[x.name,x] as const));
  for(const cap of caps) if(cap.effect!=="PURE") throw new Error("WASM extension capabilities are PURE-only");
  for(const n of nodes){
    const cap=capBy.get(n.capability);
    if(n.effect!=="PURE"||!cap) throw new Error("invalid extension node capability/effect");
    if(cap.effect!==n.effect||cap.adapter!==n.adapter) throw new Error("extension node capability contract mismatch");
  }
  for(const t of tools){
    const cap=capBy.get(t.capability);
    if(t.effect!=="PURE"||!cap||cap.effect!==t.effect) throw new Error("invalid extension tool capability/effect");
  }
  const allKinds=[...BUILTIN_NODES.map(x=>x.kind),...nodes.map(x=>x.kind)];
  const allTools=[...BUILTIN_TOOLS.map(x=>x.name),...tools.map(x=>x.name)];
  if(new Set(allKinds).size!==allKinds.length) throw new Error("extension node kind collision");
  if(new Set(allTools).size!==allTools.length) throw new Error("extension tool collision");
  const clean:ExtensionManifest={
    schema:raw.schema,extension_id:String(raw.extension_id),version:String(raw.version),host_abi:raw.host_abi,
    execution:{mode:"WASM_NO_IMPORTS",module_sha256:String(ex.module_sha256),entrypoint:"p346_run",deterministic:true,max_module_bytes:maxBytes,timeout_ms:timeout},
    capabilities:caps.sort((a,b)=>a.name.localeCompare(b.name)),
    node_kinds:nodes.sort((a,b)=>a.kind.localeCompare(b.kind)),
    tools:tools.sort((a,b)=>a.name.localeCompare(b.name)),
  };
  return {...clean,manifest_sha256:sha256(clean)};
}

function inventory(extensions:any[]=[]){
  const checked=extensions.map(validateExtensionManifest);
  const capabilities:CapabilitySpec[]=[...BUILTIN_CAPABILITIES,...checked.flatMap(x=>x.capabilities)];
  const nodes:NodeSpec[]=[...BUILTIN_NODES,...checked.flatMap(x=>x.node_kinds)];
  const tools:ToolSpec[]=[...BUILTIN_TOOLS,...checked.flatMap(x=>x.tools||[])];
  const capNames=new Set(capabilities.map(x=>x.name));
  if(capNames.size!==capabilities.length) throw new Error("capability name collision");
  const capBy=new Map(capabilities.map(x=>[x.name,x] as const));
  for(const row of [...nodes,...tools]){
    const cap=capBy.get(row.capability);
    if(!cap) throw new Error("undeclared capability: "+row.capability);
    if(cap.effect!==row.effect) throw new Error("capability/effect mismatch: "+row.capability);
  }
  for(const node of nodes){
    const cap=capBy.get(node.capability)!;
    if(cap.adapter!==node.adapter) throw new Error("capability/adapter mismatch: "+node.capability);
  }
  return {capabilities,nodes,tools};
}

export function projectToolSurface(extensions:any[]=[]){
  const rows=inventory(extensions).tools.map(t=>({
    name:t.name,description:t.description,capability:t.capability,effect:t.effect,
    annotations:annotations(t.effect),input_schema:t.input_schema,
    contract_sha256:sha256({name:t.name,capability:t.capability,effect:t.effect,input_schema:t.input_schema}),
  })).sort((a,b)=>a.name.localeCompare(b.name));
  return {schema:"chatgpt-web-hwpx-mcp/p3.46/tool-surface/v1",phase:"P3.46",tools:rows,surface_sha256:sha256(rows)};
}

function graph(plan:any){
  const nodes:any[]=Array.isArray(plan?.nodes)?plan.nodes:[];
  if(nodes.length<1||nodes.length>128) throw new Error("effect plan requires 1..128 nodes");
  const by=new Map<string,any>(), children=new Map<string,string[]>(), indegree=new Map<string,number>();
  for(const n of nodes){const id=String(n.id||"");assertId(id,"plan node id");if(by.has(id))throw new Error("duplicate plan node");by.set(id,n);children.set(id,[]);indegree.set(id,0);}
  for(const n of nodes){
    const id=String(n.id),deps:string[]=Array.isArray(n.deps)?n.deps.map(String):[];
    if(new Set(deps).size!==deps.length) throw new Error("duplicate dependency");
    for(const d of deps){if(!by.has(d))throw new Error("unknown dependency "+d);children.get(d)!.push(id);indegree.set(id,(indegree.get(id)||0)+1);}
  }
  const ready=[...indegree].filter(([,v])=>v===0).map(([k])=>k).sort(), order:string[]=[];
  while(ready.length){const id=ready.shift()!;order.push(id);for(const c of (children.get(id)||[]).sort()){const v=(indegree.get(c)||0)-1;indegree.set(c,v);if(v===0){ready.push(c);ready.sort();}}}
  if(order.length!==nodes.length) throw new Error("effect plan contains cycle");
  return {by,children,order};
}
function legalActions(effect:Effect,reusable:boolean):EffectAction[]{
  if(effect==="EXTERNAL_WORLD_CONTACT") return ["WAIT_EXTERNAL"];
  if((effect==="READ_ONLY"||effect==="PURE")&&reusable) return ["EXECUTE","REUSE"];
  return ["EXECUTE"];
}
export function validateEffectComposition(plan:any){
  if(!plan||plan.schema!=="chatgpt-web-hwpx-mcp/p3.46/effect-plan/v1") throw new Error("invalid P3.46 effect plan");
  const g=graph(plan), normalized:any[]=[];
  for(const id of g.order){
    const n=g.by.get(id),effect=String(n.effect||"") as Effect;
    if(!EFFECT_SET.has(effect)) throw new Error("invalid effect at "+id);
    const reusable=Boolean(n.reusable), action=String(n.action||"EXECUTE") as EffectAction;
    if(reusable&&!["READ_ONLY","PURE"].includes(effect)) throw new Error("non-read effect cannot be reusable at "+id);
    if(!legalActions(effect,reusable).includes(action)) throw new Error("action/effect mismatch at "+id);
    if(effect==="DELIVERY"&&(g.children.get(id)||[]).length) throw new Error("DELIVERY must be a terminal DAG sink");
    normalized.push({id,deps:[...(n.deps||[])].map(String).sort(),effect,action,reusable});
  }
  const body={schema:"chatgpt-web-hwpx-mcp/p3.46/effect-validation/v1",ok:true,topological_order:g.order,nodes:normalized};
  return {...body,validation_sha256:sha256(body)};
}
export function validateToolSequence(effects:any[]){
  if(!Array.isArray(effects)||effects.length<1||effects.length>128) throw new Error("tool sequence requires 1..128 effects");
  const rows=effects.map(String);
  for(const e of rows) if(!EFFECT_SET.has(e)) throw new Error("invalid effect in tool sequence");
  if(rows.filter(e=>e==="DELIVERY").length>1) throw new Error("tool sequence may contain at most one DELIVERY");
  const delivery=rows.indexOf("DELIVERY");
  if(delivery>=0&&delivery!==rows.length-1) throw new Error("DELIVERY must terminate tool sequence");
  const body={schema:"chatgpt-web-hwpx-mcp/p3.46/tool-sequence-validation/v1",ok:true,effects:rows};
  return {...body,sequence_sha256:sha256(body)};
}
function projectedToolMap(extensions:any[]=[]){
  const inv=inventory(extensions);
  return new Map(inv.tools.map(t=>[t.name,t] as const));
}
export function validateProjectedToolSequence(toolNames:any[],extensions:any[]=[]){
  if(!Array.isArray(toolNames)||toolNames.length<1||toolNames.length>128) throw new Error("projected tool sequence requires 1..128 tool names");
  const by=projectedToolMap(extensions),tools=toolNames.map(String);
  const rows=tools.map(name=>{
    const spec=by.get(name);
    if(!spec) throw new Error("unknown projected tool: "+name);
    return {name,capability:spec.capability,effect:spec.effect};
  });
  const validation=validateToolSequence(rows.map(row=>row.effect));
  const body={
    schema:"chatgpt-web-hwpx-mcp/p3.46/projected-tool-sequence/v1",
    phase:"P3.46",tools:rows,effects:rows.map(row=>row.effect),
    effect_validation_sha256:validation.sequence_sha256,
    derived_from_contracts:true,
  };
  return {...body,sequence_sha256:sha256(body)};
}
export function validateProjectedToolPlan(plan:any,extensions:any[]=[]){
  if(!plan||plan.schema!=="chatgpt-web-hwpx-mcp/p3.46/tool-call-plan/v1") throw new Error("invalid projected tool-call plan");
  const g=graph(plan),byTool=projectedToolMap(extensions),derivedNodes:any[]=[],bindings:any[]=[];
  for(const id of g.order){
    const raw=g.by.get(id),name=String(raw.tool||"");
    const spec=byTool.get(name);
    if(!spec) throw new Error("unknown projected tool: "+name);
    if(raw.effect!==undefined&&String(raw.effect)!==spec.effect) throw new Error("caller effect override diverges from projected tool contract at "+id);
    if(raw.capability!==undefined&&String(raw.capability)!==spec.capability) throw new Error("caller capability override diverges from projected tool contract at "+id);
    const action:EffectAction=spec.effect==="EXTERNAL_WORLD_CONTACT"?"WAIT_EXTERNAL":"EXECUTE";
    const deps=[...(raw.deps||[])].map(String).sort();
    derivedNodes.push({id,deps,effect:spec.effect,action,reusable:false});
    bindings.push({id,tool:name,capability:spec.capability,effect:spec.effect,contract_sha256:sha256({name:spec.name,capability:spec.capability,effect:spec.effect,input_schema:spec.input_schema})});
  }
  const effectPlan={schema:"chatgpt-web-hwpx-mcp/p3.46/effect-plan/v1",nodes:derivedNodes};
  const validation=validateEffectComposition(effectPlan);
  const body={
    schema:"chatgpt-web-hwpx-mcp/p3.46/projected-tool-plan-validation/v1",
    phase:"P3.46",tool_bindings:bindings,effect_plan:effectPlan,
    topological_order:validation.topological_order,
    effect_validation_sha256:validation.validation_sha256,
    derived_from_contracts:true,
  };
  return {...body,validation_sha256:sha256(body)};
}

function legacyEffect(effect:string):Effect{
  if(effect==="PURE"||effect==="DOCUMENT_MUTATION"||effect==="EXTERNAL_WORLD_CONTACT") return effect;
  throw new Error("unsupported P3.45 side effect");
}
export function inspectLegacyRuntime(state:any){
  if(!state||state.schema!=="chatgpt-web-hwpx-mcp/p3.45/runtime-run/v1") throw new Error("inspector requires P3.45 runtime state");
  const c=state.compiled||{}, ir=c.ir||{}, source:any[]=Array.isArray(ir.nodes)?ir.nodes:[];
  const nodes=source.map((n:any)=>{
    const id=String(n.id),binding=(c.provider_bindings||{})[id]||{},primary=binding.primary||{},out=(state.outputs||{})[id]||{};
    return {
      id,kind:String(n.kind||""),deps:[...(n.deps||[])],state:String((state.node_states||{})[id]||""),
      effect:legacyEffect(String((c.side_effects||{})[id]||"")),action:String((c.actions||{})[id]||""),
      affected:(c.affected_nodes||[]).includes(id),reused:(c.reused_nodes||[]).includes(id),
      provider_id:String(primary.provider_id||""),provider_version:String(primary.provider_version||""),
      adapter:String(binding.adapter||""),provider_binding_sha256:String((c.provider_binding_sha256||{})[id]||""),
      output_sha256:String(out.output_sha256||""),receipt_sha256:String(out.receipt_sha256||""),
    };
  });
  const edges:any[]=[];for(const n of nodes)for(const d of n.deps)edges.push({from:String(d),to:n.id});
  const events=(state.events||[]).map((e:any)=>({seq:Number(e.seq),name:String(e.name),node_id:e.node_id?String(e.node_id):null,revision:Number(e.revision),previous_event_hash:String(e.previous_event_hash),event_hash:String(e.event_hash),attributes:e.attributes||{}}));
  const body:any={
    schema:"chatgpt-web-hwpx-mcp/p3.46/runtime-inspector/v1",phase:"P3.46",source_runtime:"P3.45",
    run:{run_id:String(state.run_id||""),status:String(state.status||""),base_revision:Number(state.base_revision),current_revision:Number(state.current_revision),run_sha256:String(state.run_sha256||""),head_event_hash:String(state.head_event_hash||"")},
    dag:{nodes,edges,topological_order:[...(c.topological_order||[])]},
    cache:{affected_nodes:[...(c.affected_nodes||[])],reused_nodes:[...(c.reused_nodes||[])],node_spec_sha256:c.node_spec_sha256||{},provider_binding_sha256:c.provider_binding_sha256||{}},
    events,
  };
  return {...body,inspector_sha256:sha256(body)};
}
export function runtimeDiagnostics(state:any){
  const view=inspectLegacyRuntime(state),rows:any[]=[];
  for(const n of view.dag.nodes){
    if(!n.provider_id) rows.push({severity:"ERROR",code:"PROVIDER_BINDING_MISSING",node_id:n.id});
    if(n.effect==="DOCUMENT_MUTATION"&&n.action!=="EXECUTE") rows.push({severity:"ERROR",code:"MUTATION_ACTION_INVALID",node_id:n.id});
    if(n.effect==="EXTERNAL_WORLD_CONTACT"&&n.action!=="WAIT_EXTERNAL") rows.push({severity:"ERROR",code:"WORLD_CONTACT_ACTION_INVALID",node_id:n.id});
    if(n.reused&&n.effect!=="PURE") rows.push({severity:"ERROR",code:"NONPURE_REUSE_OBSERVED",node_id:n.id});
    if(n.receipt_sha256&&!/^[0-9a-f]{64}$/.test(n.receipt_sha256)) rows.push({severity:"ERROR",code:"RECEIPT_HASH_INVALID",node_id:n.id});
  }
  if(view.events.length&&view.events[view.events.length-1].event_hash!==view.run.head_event_hash) rows.push({severity:"ERROR",code:"HEAD_EVENT_HASH_DIVERGENCE"});
  const errors=rows.filter(x=>x.severity==="ERROR").length;
  return {schema:"chatgpt-web-hwpx-mcp/p3.46/runtime-diagnostics/v1",ok:errors===0,run_id:view.run.run_id,diagnostics:rows,summary:{errors,warnings:rows.length-errors},diagnostics_sha256:sha256(rows)};
}
export function codegen(extensions:any[]=[]){
  const inv=inventory(extensions),surface=projectToolSurface(extensions);
  const body={
    schema:"chatgpt-web-hwpx-mcp/p3.46/generated-contracts/v1",phase:"P3.46",
    effects:EFFECTS.map(effect=>({effect,...annotations(effect)})),
    capabilities:inv.capabilities.slice().sort((a,b)=>a.name.localeCompare(b.name)),
    node_kinds:inv.nodes.slice().sort((a,b)=>a.kind.localeCompare(b.kind)),
    tool_surface:surface,
  };
  return {...body,generated_sha256:sha256(body)};
}
export async function executeSandboxedWasm(request:any){
  const manifest=validateExtensionManifest(request?.manifest);
  const raw=String(request?.module_base64||"");
  if(!raw||raw.length>manifest.execution.max_module_bytes*2) throw new Error("encoded WASM bound exceeded");
  const bytes=Buffer.from(raw,"base64");
  if(bytes.length>manifest.execution.max_module_bytes) throw new Error("WASM module bound exceeded");
  if(shaBytes(bytes)!==manifest.execution.module_sha256) throw new Error("WASM module hash mismatch");
  assertScalarWasmResourceShape(bytes);
  const module=new WebAssembly.Module(bytes);
  if(WebAssembly.Module.imports(module).length!==0) throw new Error("sandbox denies all WASM imports");
  const instance=new WebAssembly.Instance(module,{});
  const fn:any=(instance.exports as any)[manifest.execution.entrypoint];
  if(typeof fn!=="function") throw new Error("WASM p346_run export missing");
  const value=fn();
  if(typeof value!=="number"||!Number.isSafeInteger(value)) throw new Error("p346_run must return a safe integer");
  const body={
    schema:"chatgpt-web-hwpx-mcp/p3.46/wasm-execution-receipt/v1",
    extension_id:manifest.extension_id,manifest_sha256:manifest.manifest_sha256,module_sha256:manifest.execution.module_sha256,result:value,
    sandbox:{process_isolation:true,no_imports:true,linear_memory:false,tables:false,filesystem:false,network:false,host_functions:0,timeout_ms:manifest.execution.timeout_ms},
  };
  return {...body,receipt_sha256:sha256(body)};
}

export const P346_PLATFORM_CONTRACT={
  schema:"chatgpt-web-hwpx-mcp/p3.46/developer-platform-contract/v1",
  phase:"P3.46",product:"0.23.0-p3.46",effect_types:EFFECTS,
  language_authority:{
    typescript:"TYPED_CAPABILITY_EFFECT_KERNEL_TOOL_PROJECTION_CODEGEN_INSPECTOR_AND_WASM_ABI",
    rust:"AUTHORITATIVE_EFFECT_PLAN_AND_TOOL_SEQUENCE_INVARIANT_KERNEL",
    python:"HWPX_HOST_ADAPTER_REGISTRY_AND_MCP_BINDING_ONLY",
    powershell:"HANCOM_WORLD_CONTACT_ONLY",
  },
  preexecution_rejection:{reusable_non_read_effects:true,delivery_must_be_terminal:true,action_effect_mismatch:true,unknown_capability_or_adapter:true,unknown_projected_tool:true,caller_effect_or_capability_override:true},
  extensions:{host_abi:"p3.46-extension-v1",arbitrary_in_process_loading:false,executable_boundary:"PURE_SCALAR_WASM_NO_IMPORTS_IN_SEPARATE_BOUNDED_NODE_PROCESS",wasm_imports_allowed:0,wasm_linear_memory_allowed:false,wasm_tables_allowed:false,parent_process_timeout:true,non_pure_extension_code:"REJECTED"},
  inspector:{read_only:true,fields:["transaction_dag","event_chain","cache_invalidation","provider_binding","host_receipt_hashes","run_status"]},
  hot_swap:{scope:"OWNER_SCOPED_DOCUMENT_PRE_ADMITTED_PROCESS_LOCAL_PROFILES",compare_and_swap_generation:true,rollback:true,cross_document_leakage:false,arbitrary_code_registration:false},
  generated_contracts:true,
  schema_projection:{
    authoritative_source:"TYPESCRIPT_PROJECTED_INPUT_SCHEMA",
    actual_mcp_semantic_parity_required:true,
    parity_dimensions:["PROPERTY_SET","REQUIRED_SET","DECLARED_PRIMITIVE_TYPES","TOOL_ANNOTATIONS"],
    lifecycle_authority:"OAUTH_LIST_TOOLS",
  },
  builtin_provider:{provider_id:"hwpx-mcp-core",provider_version:"p3.46",capabilities:BUILTIN_CAPABILITIES},
  builtin_node_kinds:BUILTIN_NODES.map(x=>x.kind),
  builtin_tool_surface_sha256:projectToolSurface().surface_sha256,
} as const;

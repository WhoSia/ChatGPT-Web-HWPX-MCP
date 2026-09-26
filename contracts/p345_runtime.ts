declare function require(name: string): any;
const crypto = require("crypto");

export type JsonScalar = string | number | boolean | null;
export type SideEffect = "PURE" | "DOCUMENT_MUTATION" | "EXTERNAL_WORLD_CONTACT";
export type PlanAction = "REUSE" | "EXECUTE" | "WAIT_EXTERNAL";
export type NodeState = "PENDING" | "RUNNING" | "WAITING_EXTERNAL" | "REUSED" | "COMMITTED" | "FAILED";

export interface CapabilityRequirement {
  name: string;
  min_version?: string;
  evidence?: string[];
  hard?: boolean;
}
export interface Capability {
  name: string;
  version: string;
  evidence: string[];
  deterministic: boolean;
  adapter: string;
}
export interface CapabilityProvider {
  provider_id: string;
  provider_version: string;
  capabilities: Capability[];
}
export interface ExtensionManifest {
  schema: "chatgpt-web-hwpx-mcp/p3.45/extension-manifest/v1";
  extension_id: string;
  version: string;
  host_abi: "p3.45-extension-v1";
  deterministic: boolean;
  node_kinds: Array<{
    kind: string;
    capability: string;
    adapter: string;
    side_effect: SideEffect;
    reusable?: boolean;
  }>;
}
export interface IRNode {
  id: string;
  kind: string;
  deps?: string[];
  inputs?: unknown;
  requires?: CapabilityRequirement[];
  reusable?: boolean;
}
export interface AuthoringIR {
  schema: "chatgpt-web-hwpx-mcp/p3.45/authoring-ir/v1";
  ir_id: string;
  document_id: string;
  base_revision: number;
  nodes: IRNode[];
  outputs?: string[];
}
export interface PriorNodeSnapshot {
  node_spec_sha256: string;
  provider_binding_sha256: string;
  output_sha256: string;
  terminal_state: "COMMITTED" | "REUSED";
}
export interface CompileRequest {
  ir: AuthoringIR;
  providers?: CapabilityProvider[];
  extensions?: ExtensionManifest[];
  prior_snapshot?: Record<string, PriorNodeSnapshot>;
  changed_node_ids?: string[];
}
export interface RuntimeEventBody {
  name: "RUN_CREATED" | "NODE_REUSED" | "NODE_STARTED" | "NODE_WAITING_EXTERNAL" | "NODE_COMMITTED" | "NODE_FAILED" | "RUN_COMPLETED";
  run_id: string;
  node_id?: string;
  revision: number;
  attributes: Record<string, JsonScalar>;
}
export interface RuntimeEvent extends RuntimeEventBody {
  seq: number;
  previous_event_hash: string;
  event_hash: string;
}

const NODE_KINDS: Record<string,{capability:string;adapter:string;side_effect:SideEffect;reusable:boolean}> = {
  "document.snapshot": {capability:"document.inspect",adapter:"DOCUMENT_SNAPSHOT",side_effect:"PURE",reusable:true},
  "document.text.edit": {capability:"document.text.edit",adapter:"DOCUMENT_TEXT_EDIT",side_effect:"DOCUMENT_MUTATION",reusable:false},
  "document.format.edit": {capability:"document.format.edit",adapter:"DOCUMENT_FORMAT_EDIT",side_effect:"DOCUMENT_MUTATION",reusable:false},
  "document.design.repair": {capability:"document.design.repair",adapter:"DOCUMENT_DESIGN_REPAIR",side_effect:"DOCUMENT_MUTATION",reusable:false},
  "document.render.evidence": {capability:"document.render.evidence",adapter:"EXTERNAL_RENDER",side_effect:"EXTERNAL_WORLD_CONTACT",reusable:false},
};

export const BUILTIN_PROVIDER: CapabilityProvider = {
  provider_id:"hwpx-mcp-core",
  provider_version:"p3.45",
  capabilities:[
    {name:"document.inspect",version:"1.0.0",evidence:["STRUCTURAL_NATIVE_FACT"],deterministic:true,adapter:"DOCUMENT_SNAPSHOT"},
    {name:"document.text.edit",version:"1.0.0",evidence:["REVISION_CAS","PACKAGE_VALIDATION"],deterministic:true,adapter:"DOCUMENT_TEXT_EDIT"},
    {name:"document.format.edit",version:"1.0.0",evidence:["REVISION_CAS","PACKAGE_VALIDATION"],deterministic:true,adapter:"DOCUMENT_FORMAT_EDIT"},
    {name:"document.design.repair",version:"1.0.0",evidence:["P3.42_MUTATION_FOOTPRINT","P3.43_POLICY_COMPATIBLE"],deterministic:true,adapter:"DOCUMENT_DESIGN_REPAIR"},
    {name:"document.render.evidence",version:"1.0.0",evidence:["EXTERNAL_WORLD_CONTACT"],deterministic:false,adapter:"EXTERNAL_RENDER"},
  ],
};

function assertId(value:string,label:string):void{
  if(!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(value||"")) throw new Error("invalid "+label);
}
function assertDeterministic(value:any,path="$"):void{
  if(value===null||typeof value==="string"||typeof value==="boolean") return;
  if(typeof value==="number"){
    if(!Number.isSafeInteger(value)) throw new Error("deterministic payload requires safe integers at "+path);
    return;
  }
  if(Array.isArray(value)){ value.forEach((v,i)=>assertDeterministic(v,path+"["+i+"]")); return; }
  if(typeof value==="object"){
    for(const key of Object.keys(value)){
      if(value[key]===undefined) throw new Error("undefined is not deterministic at "+path+"."+key);
      assertDeterministic(value[key],path+"."+key);
    }
    return;
  }
  throw new Error("unsupported deterministic value at "+path);
}
export function canonicalJson(value:any):string{
  assertDeterministic(value);
  if(value===null) return "null";
  if(typeof value==="string"||typeof value==="boolean"||typeof value==="number") return JSON.stringify(value);
  if(Array.isArray(value)) return "["+value.map(canonicalJson).join(",")+"]";
  const keys=Object.keys(value).sort();
  return "{"+keys.map(k=>JSON.stringify(k)+":"+canonicalJson(value[k])).join(",")+"}";
}
export function sha256(value:any):string{
  return crypto.createHash("sha256").update(canonicalJson(value),"utf8").digest("hex");
}
function versionTuple(v:string):number[]{
  if(!/^\d+(\.\d+){0,2}$/.test(v||"")) throw new Error("invalid semantic version");
  return v.split(".").map(Number).concat([0,0,0]).slice(0,3);
}
function atLeast(actual:string,minimum:string):boolean{
  const a=versionTuple(actual),b=versionTuple(minimum);
  for(let i=0;i<3;i++){ if(a[i]!==b[i]) return a[i]>b[i]; }
  return true;
}
export function validateExtensionManifest(raw:ExtensionManifest):ExtensionManifest & {manifest_sha256:string}{
  if(!raw||raw.schema!=="chatgpt-web-hwpx-mcp/p3.45/extension-manifest/v1"||raw.host_abi!=="p3.45-extension-v1") throw new Error("invalid P3.45 extension manifest");
  assertId(raw.extension_id,"extension_id");
  if(!raw.version||!/^\d+(\.\d+){0,2}$/.test(raw.version)) throw new Error("invalid extension version");
  if(!Array.isArray(raw.node_kinds)||raw.node_kinds.length<1||raw.node_kinds.length>32) throw new Error("extension node_kinds must contain 1..32 entries");
  const seen=new Set<string>();
  for(const row of raw.node_kinds){
    assertId(row.kind,"extension node kind");
    assertId(row.capability,"extension capability");
    assertId(row.adapter,"extension adapter");
    if(seen.has(row.kind)||NODE_KINDS[row.kind]) throw new Error("extension node kind collision");
    seen.add(row.kind);
    if(!["PURE","DOCUMENT_MUTATION","EXTERNAL_WORLD_CONTACT"].includes(row.side_effect)) throw new Error("invalid extension side effect");
    if(row.reusable&&row.side_effect!=="PURE") throw new Error("only PURE extension nodes may be reusable");
  }
  const clean=JSON.parse(JSON.stringify(raw));
  return {...clean,manifest_sha256:sha256(clean)};
}
function nodeKindTable(extensions:ExtensionManifest[]):Record<string,{capability:string;adapter:string;side_effect:SideEffect;reusable:boolean}>{
  const table={...NODE_KINDS};
  for(const extRaw of extensions){
    const ext=validateExtensionManifest(extRaw);
    for(const row of ext.node_kinds){
      if(table[row.kind]) throw new Error("node kind collision: "+row.kind);
      table[row.kind]={capability:row.capability,adapter:row.adapter,side_effect:row.side_effect,reusable:Boolean(row.reusable)};
    }
  }
  return table;
}
function topo(nodes:IRNode[]):string[]{
  if(nodes.length<1||nodes.length>64) throw new Error("authoring IR requires 1..64 nodes");
  const by=new Map<string,IRNode>();
  for(const n of nodes){ assertId(n.id,"node id"); if(by.has(n.id)) throw new Error("duplicate node id"); by.set(n.id,n); }
  const indegree=new Map<string,number>(), children=new Map<string,string[]>();
  for(const n of nodes){ indegree.set(n.id,0);children.set(n.id,[]); }
  for(const n of nodes){
    const deps=n.deps||[];
    if(new Set(deps).size!==deps.length) throw new Error("duplicate dependency");
    for(const d of deps){ if(!by.has(d)) throw new Error("unknown dependency "+d); indegree.set(n.id,(indegree.get(n.id)||0)+1);children.get(d)!.push(n.id); }
  }
  const ready=[...indegree].filter(([,v])=>v===0).map(([k])=>k).sort(), out:string[]=[];
  while(ready.length){ const id=ready.shift()!;out.push(id);for(const child of children.get(id)!.sort()){const v=(indegree.get(child)||0)-1;indegree.set(child,v);if(v===0){ready.push(child);ready.sort();}} }
  if(out.length!==nodes.length) throw new Error("authoring IR contains a cycle");
  return out;
}
function negotiate(requirements:CapabilityRequirement[],providers:CapabilityProvider[]){
  const selected:Record<string,any>={}, missingSoft:string[]=[];
  for(const req of requirements){
    assertId(req.name,"capability requirement");
    const candidates:any[]=[];
    for(const provider of providers){
      assertId(provider.provider_id,"provider id");
      for(const cap of provider.capabilities||[]){
        if(cap.name!==req.name) continue;
        if(req.min_version&&!atLeast(cap.version,req.min_version)) continue;
        const evidence=new Set(cap.evidence||[]);
        if((req.evidence||[]).some(e=>!evidence.has(e))) continue;
        candidates.push({provider_id:provider.provider_id,provider_version:provider.provider_version,capability:cap});
      }
    }
    candidates.sort((a,b)=>{
      if(Boolean(a.capability.deterministic)!==Boolean(b.capability.deterministic)) return a.capability.deterministic?-1:1;
      return (a.provider_id+"@"+a.capability.version).localeCompare(b.provider_id+"@"+b.capability.version);
    });
    if(!candidates.length){
      if(req.hard===false){missingSoft.push(req.name);continue;}
      throw new Error("required capability unavailable: "+req.name);
    }
    selected[req.name]=candidates[0];
  }
  return {selected,missing_soft:missingSoft};
}
export function compileAuthoringIR(request:CompileRequest){
  const ir=request.ir;
  if(!ir||ir.schema!=="chatgpt-web-hwpx-mcp/p3.45/authoring-ir/v1") throw new Error("invalid P3.45 authoring IR");
  assertId(ir.ir_id,"ir_id"); assertId(ir.document_id,"document_id");
  if(!Number.isInteger(ir.base_revision)||ir.base_revision<1) throw new Error("base_revision must be >=1");
  const order=topo(ir.nodes), by=new Map(ir.nodes.map(n=>[n.id,n]));
  const extensions=request.extensions||[], kinds=nodeKindTable(extensions);
  const providers=[BUILTIN_PROVIDER,...(request.providers||[])];
  const bindings:Record<string,any>={}, bindingHashes:Record<string,string>={}, specs:Record<string,string>={}, actions:Record<string,PlanAction>={}, sideEffects:Record<string,SideEffect>={};
  const directDirty=new Set<string>(request.changed_node_ids||[]);
  const prior=request.prior_snapshot||{};
  for(const id of order){
    const n=by.get(id)!;const kind=kinds[n.kind];if(!kind) throw new Error("unsupported node kind: "+n.kind);
    const requirements:[CapabilityRequirement,...CapabilityRequirement[]]=[{name:kind.capability,hard:true},...(n.requires||[])] as any;
    const negotiation=negotiate(requirements,providers);
    const binding={kind:n.kind,adapter:kind.adapter,primary:negotiation.selected[kind.capability],all:negotiation.selected,missing_soft:negotiation.missing_soft};
    bindings[id]=binding;bindingHashes[id]=sha256(binding);sideEffects[id]=kind.side_effect;
    specs[id]=sha256({id:n.id,kind:n.kind,deps:[...(n.deps||[])].sort(),inputs:n.inputs??null,requires:n.requires||[],reusable:Boolean(n.reusable??kind.reusable)});
    const bindHash=bindingHashes[id], prev=prior[id];
    if(!prev||prev.node_spec_sha256!==specs[id]||prev.provider_binding_sha256!==bindHash) directDirty.add(id);
    if(kind.side_effect!=="PURE") directDirty.add(id);
  }
  const children:Record<string,string[]>={};for(const id of order)children[id]=[];
  for(const n of ir.nodes)for(const d of n.deps||[])children[d].push(n.id);
  const dirty=new Set(directDirty), queue=[...directDirty];
  while(queue.length){const id=queue.shift()!;for(const c of children[id]||[])if(!dirty.has(c)){dirty.add(c);queue.push(c);}}
  for(const id of order){
    const n=by.get(id)!,kind=kinds[n.kind],prev=prior[id], reusable=Boolean(n.reusable??kind.reusable);
    if(kind.side_effect==="EXTERNAL_WORLD_CONTACT") actions[id]="WAIT_EXTERNAL";
    else if(kind.side_effect==="PURE"&&reusable&&!dirty.has(id)&&prev&&prev.output_sha256) actions[id]="REUSE";
    else actions[id]="EXECUTE";
  }
  const normalizedIR={...ir,nodes:ir.nodes.map(n=>({...n,deps:[...(n.deps||[])].sort(),inputs:n.inputs??null,requires:n.requires||[]}))};
  const compiled={
    schema:"chatgpt-web-hwpx-mcp/p3.45/compiled-runtime-plan/v1",phase:"P3.45",
    ir:normalizedIR,ir_sha256:sha256(normalizedIR),topological_order:order,
    node_spec_sha256:specs,provider_bindings:bindings,provider_binding_sha256:bindingHashes,side_effects:sideEffects,actions,
    affected_nodes:order.filter(id=>dirty.has(id)),reused_nodes:order.filter(id=>actions[id]==="REUSE"),
    extension_sha256:extensions.map(e=>validateExtensionManifest(e).manifest_sha256).sort(),
    prior_snapshot: prior,
  };
  return {...compiled,plan_sha256:sha256(compiled)};
}
function eventHash(previous:string,seq:number,body:RuntimeEventBody):string{
  return crypto.createHash("sha256").update("p3.45-event-v1\0"+previous+"\0"+String(seq)+"\0"+canonicalJson(body),"utf8").digest("hex");
}
function append(state:any,body:RuntimeEventBody){
  const seq=(state.events?.length||0)+1, previous=state.head_event_hash||"GENESIS";
  const ev:RuntimeEvent={...body,seq,previous_event_hash:previous,event_hash:eventHash(previous,seq,body)};
  state.events=[...(state.events||[]),ev];state.head_event_hash=ev.event_hash;return ev;
}
function terminal(v:NodeState){return v==="COMMITTED"||v==="REUSED";}
export function createRun(compiled:any){
  const states:Record<string,NodeState>={};for(const id of compiled.topological_order)states[id]="PENDING";
  const runId="p345_"+sha256({ir_sha256:compiled.ir_sha256,plan_sha256:compiled.plan_sha256,document_id:compiled.ir.document_id,base_revision:compiled.ir.base_revision}).slice(0,24);
  const state:any={schema:"chatgpt-web-hwpx-mcp/p3.45/runtime-run/v1",phase:"P3.45",run_id:runId,document_id:compiled.ir.document_id,base_revision:compiled.ir.base_revision,current_revision:compiled.ir.base_revision,status:"READY",compiled,node_states:states,outputs:{},events:[],head_event_hash:"GENESIS"};
  append(state,{name:"RUN_CREATED",run_id:runId,revision:state.current_revision,attributes:{ir_sha256:compiled.ir_sha256,plan_sha256:compiled.plan_sha256}});
  for(const id of compiled.topological_order){
    if(compiled.actions[id]==="REUSE"){
      const priorOutput=(compiled as any).prior_snapshot?.[id]?.output_sha256||"";
      state.node_states[id]="REUSED";state.outputs[id]={output_sha256:priorOutput};
      append(state,{name:"NODE_REUSED",run_id:runId,node_id:id,revision:state.current_revision,attributes:{output_sha256:priorOutput}});
    }
  }
  return reseal(state);
}
function reseal(state:any){const clean={...state};delete clean.run_sha256;state.run_sha256=sha256(clean);return state;}
function depsReady(state:any,id:string){const n=state.compiled.ir.nodes.find((x:any)=>x.id===id);return (n.deps||[]).every((d:string)=>terminal(state.node_states[d]));}
export function transitionRuntime(input:{state:any;command:any}){
  const state=JSON.parse(JSON.stringify(input.state)), c=input.command||{}, id=String(c.node_id||"");
  if(state.schema!=="chatgpt-web-hwpx-mcp/p3.45/runtime-run/v1") throw new Error("invalid runtime state");
  if(c.type!=="COMPLETE_RUN"){if(!state.node_states[id])throw new Error("unknown node");if(!depsReady(state,id))throw new Error("node dependencies are not terminal");}
  if(c.type==="START_NODE"){
    if(state.compiled.actions[id]!=="EXECUTE"||state.node_states[id]!=="PENDING")throw new Error("node cannot start");
    state.node_states[id]="RUNNING";state.status="RUNNING";
    append(state,{name:"NODE_STARTED",run_id:state.run_id,node_id:id,revision:state.current_revision,attributes:{adapter:String(state.compiled.provider_bindings[id].adapter)}});
  }else if(c.type==="COMMIT_NODE"){
    if(state.node_states[id]!=="RUNNING")throw new Error("node is not running");
    const rev=Number(c.revision);if(!Number.isInteger(rev)||rev<state.current_revision)throw new Error("invalid committed revision");
    const out=String(c.output_sha256||"");if(!/^[0-9a-f]{64}$/.test(out))throw new Error("output_sha256 required");
    state.node_states[id]="COMMITTED";state.current_revision=rev;state.outputs[id]={output_sha256:out,receipt_sha256:String(c.receipt_sha256||"")};
    append(state,{name:"NODE_COMMITTED",run_id:state.run_id,node_id:id,revision:rev,attributes:{output_sha256:out,receipt_sha256:String(c.receipt_sha256||"")}});
  }else if(c.type==="WAIT_NODE"){
    if(state.compiled.actions[id]!=="WAIT_EXTERNAL"||state.node_states[id]!=="PENDING")throw new Error("node cannot wait");
    state.node_states[id]="WAITING_EXTERNAL";state.status="WAIT_EXTERNAL";
    append(state,{name:"NODE_WAITING_EXTERNAL",run_id:state.run_id,node_id:id,revision:state.current_revision,attributes:{capability:String(state.compiled.provider_bindings[id].primary.capability.name)}});
  }else if(c.type==="RESOLVE_NODE"){
    if(state.node_states[id]!=="WAITING_EXTERNAL")throw new Error("node is not waiting");
    const out=String(c.output_sha256||"");if(!/^[0-9a-f]{64}$/.test(out))throw new Error("output_sha256 required");
    state.node_states[id]="COMMITTED";state.outputs[id]={output_sha256:out,receipt_sha256:String(c.receipt_sha256||"")};state.status="RUNNING";
    append(state,{name:"NODE_COMMITTED",run_id:state.run_id,node_id:id,revision:state.current_revision,attributes:{output_sha256:out,receipt_sha256:String(c.receipt_sha256||""),external:true}});
  }else if(c.type==="FAIL_NODE"){
    if(!["RUNNING","WAITING_EXTERNAL"].includes(state.node_states[id]))throw new Error("node cannot fail");
    state.node_states[id]="FAILED";state.status="HOLD";
    append(state,{name:"NODE_FAILED",run_id:state.run_id,node_id:id,revision:state.current_revision,attributes:{"error.type":String(c.error_type||"runtime.error")}});
  }else if(c.type==="COMPLETE_RUN"){
    if(Object.values(state.node_states).some(v=>!terminal(v as NodeState)))throw new Error("run has non-terminal nodes");
    state.status="COMPLETED";append(state,{name:"RUN_COMPLETED",run_id:state.run_id,revision:state.current_revision,attributes:{head_nodes:Object.keys(state.node_states).length}});
  }else throw new Error("unknown runtime command");
  return reseal(state);
}
export function timeTravel(state:any,seq:number){
  if(!Number.isInteger(seq)||seq<1||seq>state.events.length)throw new Error("invalid event seq");
  const nodes:Record<string,NodeState>={};for(const id of state.compiled.topological_order)nodes[id]="PENDING";
  let revision=state.base_revision,status="READY";
  for(const ev of state.events.slice(0,seq)){
    revision=ev.revision;
    if(ev.name==="NODE_REUSED")nodes[ev.node_id]="REUSED";
    else if(ev.name==="NODE_STARTED")nodes[ev.node_id]="RUNNING";
    else if(ev.name==="NODE_WAITING_EXTERNAL")nodes[ev.node_id]="WAITING_EXTERNAL";
    else if(ev.name==="NODE_COMMITTED")nodes[ev.node_id]="COMMITTED";
    else if(ev.name==="NODE_FAILED"){nodes[ev.node_id]="FAILED";status="HOLD";}
    else if(ev.name==="RUN_COMPLETED")status="COMPLETED";
  }
  return {schema:"chatgpt-web-hwpx-mcp/p3.45/time-travel/v1",run_id:state.run_id,event_seq:seq,revision,node_states:nodes,status,head_event_hash:state.events[seq-1].event_hash};
}
export function observability(state:any){
  const counts:Record<string,number>={};for(const ev of state.events)counts[ev.name]=(counts[ev.name]||0)+1;
  return {schema:"chatgpt-web-hwpx-mcp/p3.45/observability/v1",run_id:state.run_id,status:state.status,event_count:state.events.length,event_counts:counts,reused_nodes:Object.values(state.node_states).filter(x=>x==="REUSED").length,committed_nodes:Object.values(state.node_states).filter(x=>x==="COMMITTED").length,failed_nodes:Object.values(state.node_states).filter(x=>x==="FAILED").length,base_revision:state.base_revision,current_revision:state.current_revision,head_event_hash:state.head_event_hash,attributes:{"service.name":"chatgpt-web-hwpx-mcp","hwpx.phase":"P3.45"}};
}
export const P345_RUNTIME_CONTRACT={
  schema:"chatgpt-web-hwpx-mcp/p3.45/runtime-contract/v1",phase:"P3.45",host_abi:"p3.45-extension-v1",
  language_authority:{typescript:"PRIMARY_IR_COMPILER_SCHEDULER_AND_RUNTIME_STATE_MACHINE",rust:"AUTHORITATIVE_EVENT_REPLAY_AND_INVARIANT_KERNEL",python:"HWPX_HOST_ADAPTER_AND_MCP_BINDING_ONLY",powershell:"HANCOM_WORLD_CONTACT_ONLY"},
  incremental_recompilation:{pure_node_reuse_only:true,document_mutations_never_cache_reused:true,external_world_contact_never_cache_reused:true,transitive_invalidation:true},
  deterministic_payload:{canonical_json:"JCS_COMPATIBLE_SAFE_INTEGER_SUBSET",timestamps_excluded_from_hash:true,floats_forbidden:true},
  builtin_provider:BUILTIN_PROVIDER,supported_builtin_node_kinds:Object.keys(NODE_KINDS).sort(),
  extensions:{dynamic_code_loading:false,manifest_only:true,host_adapter_allowlist:true},
  observability:{event_names_low_cardinality:true,deterministic_event_core_separate_from_observation_time:true},
  non_claims:["Runtime replay does not recreate external world contact.","A cached PURE node does not authorize reuse of a document mutation.","Extension manifests do not load arbitrary code."]
} as const;

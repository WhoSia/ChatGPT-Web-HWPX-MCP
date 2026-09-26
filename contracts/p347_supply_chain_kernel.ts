declare function require(name:string):any;
declare const Buffer:any;
const crypto=require("crypto");
import {
  canonicalJson,
  sha256,
  validateExtensionManifest,
} from "./p346_capability_kernel";

export type CompatibilityVerdict=
  "SAFE_DROP_IN"|"MIGRATION_REQUIRED"|"REPLAY_BREAKING"|"EFFECT_ESCALATION"|"INCOMPATIBLE";
export type RolloutState=
  "INSTALLED"|"CANDIDATE"|"SHADOW"|"CANARY"|"PROMOTED"|"RETIRED";

export interface DigestRef {sha256:string}
export interface DependencyRef {
  package_id:string;
  extension_id:string;
  version:string;
}
export interface BuildAttestation {
  schema:"chatgpt-web-hwpx-mcp/p3.47/build-attestation/v1";
  predicate_type:"https://slsa.dev/provenance/v1";
  builder:{id:string};
  build_type:string;
  source:{uri:string;revision:string;sha256:string};
  invocation:{parameters:any};
  materials:{uri:string;sha256:string}[];
  subjects:{name:string;sha256:string}[];
  reproducible:boolean;
}
export interface ExtensionPackage {
  schema:"chatgpt-web-hwpx-mcp/p3.47/extension-package/v1";
  extension:any;
  module_base64:string;
  dependencies:DependencyRef[];
  build_attestation:BuildAttestation;
}
export interface HostObservation {
  host_id:string;
  semantic_sha256:string;
  mutation_footprint_sha256:string;
  revision_delta:number;
  package_part_sha256:string;
  render_observable_sha256?:string;
}
export interface CertificationEvidence {
  gate:string;
  status:"PASS"|"FAIL";
  evidence_sha256:string;
}

const HEX64=/^[0-9a-f]{64}$/;
const PKG=/^sha256:[0-9a-f]{64}$/;
const REQUIRED_GATES=[
  "MANIFEST_VALID",
  "MODULE_HASH_BOUND",
  "PROVENANCE_SUBJECT_BOUND",
  "DEPENDENCY_CLOSURE_VALID",
  "DETERMINISM_REPLAY_PASS",
  "SANDBOX_PASS",
  "HOST_CONFORMANCE_PASS",
  "NEGATIVE_CONTROLS_PASS",
];
const STATES:RolloutState[]=[
  "INSTALLED","CANDIDATE","SHADOW","CANARY","PROMOTED","RETIRED"
];
const ALLOWED_TRANSITIONS:Record<RolloutState,RolloutState[]>={
  INSTALLED:["CANDIDATE","RETIRED"],
  CANDIDATE:["SHADOW","RETIRED"],
  SHADOW:["CANARY","RETIRED"],
  CANARY:["PROMOTED","RETIRED"],
  PROMOTED:["RETIRED"],
  RETIRED:[],
};
const EFFECT_RISK:Record<string,number>={
  READ_ONLY:0,
  PURE:0,
  RUNTIME_CONFIGURATION:2,
  DOCUMENT_MUTATION:3,
  EXTERNAL_WORLD_CONTACT:4,
  DELIVERY:5,
};

function assertId(v:string,label:string){
  if(!/^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}$/.test(String(v||""))) throw new Error("invalid "+label);
}
function assertHex(v:string,label:string){
  if(!HEX64.test(String(v||""))) throw new Error("invalid "+label);
}
function decodeBase64Strict(v:string):any{
  if(typeof v!=="string"||v.length<4||v.length>100000) throw new Error("invalid module_base64");
  const clean=v.replace(/\s+/g,"");
  if(!/^[A-Za-z0-9+/]*={0,2}$/.test(clean)||clean.length%4!==0) throw new Error("invalid module_base64");
  const bytes=Buffer.from(clean,"base64");
  if(bytes.toString("base64").replace(/=+$/,"")!==clean.replace(/=+$/,"")) throw new Error("invalid module_base64");
  return bytes;
}
function byteSha(bytes:any):string{
  return crypto.createHash("sha256").update(bytes).digest("hex");
}
function cleanDependency(raw:any):DependencyRef{
  if(!raw||typeof raw!=="object") throw new Error("dependency must be object");
  const package_id=String(raw.package_id||"");
  if(!PKG.test(package_id)) throw new Error("invalid dependency package_id");
  assertId(String(raw.extension_id||""),"dependency extension_id");
  if(!/^\d+(\.\d+){0,2}$/.test(String(raw.version||""))) throw new Error("invalid dependency version");
  return {package_id,extension_id:String(raw.extension_id),version:String(raw.version)};
}
function cleanAttestation(raw:any,manifestSha:string,moduleSha:string):BuildAttestation{
  if(!raw||raw.schema!=="chatgpt-web-hwpx-mcp/p3.47/build-attestation/v1") throw new Error("invalid P3.47 build attestation");
  if(raw.predicate_type!=="https://slsa.dev/provenance/v1") throw new Error("unsupported provenance predicate_type");
  assertId(String(raw.builder?.id||""),"builder id");
  assertId(String(raw.build_type||""),"build_type");
  const source=raw.source||{};
  if(typeof source.uri!=="string"||!source.uri.trim()) throw new Error("invalid source uri");
  if(typeof source.revision!=="string"||!source.revision.trim()) throw new Error("invalid source revision");
  assertHex(String(source.sha256||""),"source sha256");
  const materials=(Array.isArray(raw.materials)?raw.materials:[]).map((m:any)=>{
    if(!m||typeof m.uri!=="string"||!m.uri.trim()) throw new Error("invalid material uri");
    assertHex(String(m.sha256||""),"material sha256");
    return {uri:String(m.uri),sha256:String(m.sha256)};
  }).sort((a:any,b:any)=>a.uri.localeCompare(b.uri)||a.sha256.localeCompare(b.sha256));
  if(materials.length>128) throw new Error("too many provenance materials");
  const subjects=(Array.isArray(raw.subjects)?raw.subjects:[]).map((s:any)=>{
    if(!s||typeof s.name!=="string"||!s.name.trim()) throw new Error("invalid subject name");
    assertHex(String(s.sha256||""),"subject sha256");
    return {name:String(s.name),sha256:String(s.sha256)};
  }).sort((a:any,b:any)=>a.name.localeCompare(b.name));
  const subj=new Map(subjects.map((x:any)=>[x.name,x.sha256]));
  if(subj.get("extension-manifest.json")!==manifestSha) throw new Error("provenance manifest subject mismatch");
  if(subj.get("module.wasm")!==moduleSha) throw new Error("provenance module subject mismatch");
  return {
    schema:raw.schema,
    predicate_type:raw.predicate_type,
    builder:{id:String(raw.builder.id)},
    build_type:String(raw.build_type),
    source:{uri:String(source.uri),revision:String(source.revision),sha256:String(source.sha256)},
    invocation:{parameters:JSON.parse(JSON.stringify(raw.invocation?.parameters??{}))},
    materials,
    subjects,
    reproducible:raw.reproducible===true,
  };
}
function capabilityMap(manifest:any):Map<string,any>{
  return new Map((manifest.capabilities||[]).map((x:any)=>[x.name,x]));
}
function toolMap(manifest:any):Map<string,any>{
  return new Map((manifest.tools||[]).map((x:any)=>[x.name,x]));
}
function schemaBackwardCompatible(oldSchema:any,newSchema:any):boolean{
  if(!oldSchema||!newSchema||oldSchema.type!=="object"||newSchema.type!=="object") return canonicalJson(oldSchema)===canonicalJson(newSchema);
  const oldProps=oldSchema.properties||{}, newProps=newSchema.properties||{};
  const oldReq=new Set<string>((oldSchema.required||[]).map(String));
  const newReq=new Set<string>((newSchema.required||[]).map(String));
  for(const key of newReq) if(!oldReq.has(key)) return false;
  for(const key of Object.keys(oldProps)){
    if(!(key in newProps)) return false;
    const a=oldProps[key]||{},b=newProps[key]||{};
    if((a.type||null)!==(b.type||null)) return false;
    if(a.type==="array"&&((a.items||{}).type||null)!==((b.items||{}).type||null)) return false;
  }
  return true;
}

export function normalizePackage(raw:any){
  if(!raw||raw.schema!=="chatgpt-web-hwpx-mcp/p3.47/extension-package/v1") throw new Error("invalid P3.47 extension package");
  const extension=validateExtensionManifest(raw.extension);
  const moduleBytes=decodeBase64Strict(String(raw.module_base64||""));
  const moduleSha=byteSha(moduleBytes);
  if(moduleSha!==extension.execution.module_sha256) throw new Error("package module hash mismatch");
  if(moduleBytes.length>extension.execution.max_module_bytes) throw new Error("package module exceeds manifest bound");
  const manifestClean:any={...extension}; delete manifestClean.manifest_sha256;
  const manifestSha=sha256(manifestClean);
  if(manifestSha!==extension.manifest_sha256) throw new Error("extension manifest seal mismatch");
  const deps=(Array.isArray(raw.dependencies)?raw.dependencies:[]).map(cleanDependency)
    .sort((a:any,b:any)=>a.extension_id.localeCompare(b.extension_id)||a.package_id.localeCompare(b.package_id));
  if(new Set(deps.map((x:any)=>x.extension_id)).size!==deps.length) throw new Error("duplicate dependency extension_id");
  const build=cleanAttestation(raw.build_attestation,manifestSha,moduleSha);
  const artifact={
    extension_id:extension.extension_id,
    version:extension.version,
    manifest_sha256:manifestSha,
    module_sha256:moduleSha,
  };
  const artifact_sha256=sha256(artifact);
  const build_attestation_sha256=sha256(build);
  const packageDescriptor={
    artifact_sha256,
    dependencies:deps,
    build_attestation_sha256,
  };
  const package_sha256=sha256(packageDescriptor);
  return {
    schema:raw.schema,
    package_id:"sha256:"+package_sha256,
    package_sha256,
    artifact_sha256,
    extension,
    module_sha256:moduleSha,
    manifest_sha256:manifestSha,
    dependencies:deps,
    build_attestation:build,
    build_attestation_sha256,
    identity_authority:"CONTENT_ADDRESSED_PACKAGE_ID",
  };
}

export function verifyDependencyClosure(root:any,catalog:any[]){
  const rootPkg=normalizePackage(root);
  const normalized=(Array.isArray(catalog)?catalog:[]).map(normalizePackage);
  const by=new Map(normalized.map((x:any)=>[x.package_id,x]));
  by.set(rootPkg.package_id,rootPkg);
  const visiting=new Set<string>(),visited=new Set<string>(),order:string[]=[];
  const walk=(id:string)=>{
    if(visited.has(id)) return;
    if(visiting.has(id)) throw new Error("dependency cycle");
    const pkg=by.get(id); if(!pkg) throw new Error("missing dependency package "+id);
    visiting.add(id);
    for(const dep of pkg.dependencies){
      const target=by.get(dep.package_id);
      if(!target) throw new Error("missing dependency package "+dep.package_id);
      if(target.extension.extension_id!==dep.extension_id||target.extension.version!==dep.version) throw new Error("dependency identity/version mismatch");
      walk(dep.package_id);
    }
    visiting.delete(id);visited.add(id);order.push(id);
  };
  walk(rootPkg.package_id);
  return {
    schema:"chatgpt-web-hwpx-mcp/p3.47/dependency-closure/v1",
    root_package_id:rootPkg.package_id,
    topological_order:order,
    package_count:order.length,
    closure_sha256:sha256(order),
    authority:"EXACT_CONTENT_ADDRESSED_DEPENDENCY_CLOSURE_PASS",
  };
}

export function compareReproducibleBuilds(a:any,b:any){
  const left=normalizePackage(a),right=normalizePackage(b);
  const sameSource=canonicalJson(left.build_attestation.source)===canonicalJson(right.build_attestation.source);
  const sameMaterials=canonicalJson(left.build_attestation.materials)===canonicalJson(right.build_attestation.materials);
  const sameInvocation=canonicalJson(left.build_attestation.invocation)===canonicalJson(right.build_attestation.invocation);
  const sameArtifact=left.artifact_sha256===right.artifact_sha256;
  const reproducible=left.build_attestation.reproducible&&right.build_attestation.reproducible&&sameSource&&sameMaterials&&sameInvocation&&sameArtifact;
  return {
    schema:"chatgpt-web-hwpx-mcp/p3.47/reproducibility-comparison/v1",
    reproducible,
    same_source:sameSource,
    same_materials:sameMaterials,
    same_invocation:sameInvocation,
    same_artifact:sameArtifact,
    left_artifact_sha256:left.artifact_sha256,
    right_artifact_sha256:right.artifact_sha256,
    authority:reproducible?"REPRODUCIBLE_BUILD_ATTESTATION_PASS":"REPRODUCIBLE_BUILD_ATTESTATION_FAIL",
  };
}

export function solveCompatibility(currentRaw:any,candidateRaw:any){
  const current=normalizePackage(currentRaw),candidate=normalizePackage(candidateRaw);
  const reasons:string[]=[];
  let verdict:CompatibilityVerdict="SAFE_DROP_IN";
  if(current.extension.extension_id!==candidate.extension.extension_id){
    return {schema:"chatgpt-web-hwpx-mcp/p3.47/compatibility/v1",verdict:"INCOMPATIBLE" as CompatibilityVerdict,reasons:["EXTENSION_ID_CHANGED"]};
  }
  if(current.extension.host_abi!==candidate.extension.host_abi){
    return {schema:"chatgpt-web-hwpx-mcp/p3.47/compatibility/v1",verdict:"INCOMPATIBLE" as CompatibilityVerdict,reasons:["HOST_ABI_CHANGED"]};
  }
  const oldCaps=capabilityMap(current.extension),newCaps=capabilityMap(candidate.extension);
  for(const [name,oldCap] of oldCaps){
    const next=newCaps.get(name);
    if(!next){verdict="REPLAY_BREAKING";reasons.push("CAPABILITY_REMOVED:"+name);continue;}
    const oldRisk=EFFECT_RISK[String(oldCap.effect)]??99,nextRisk=EFFECT_RISK[String(next.effect)]??99;
    if(nextRisk>oldRisk){verdict="EFFECT_ESCALATION";reasons.push("EFFECT_ESCALATION:"+name);continue;}
    if(oldCap.adapter!==next.adapter){
      if(verdict!=="EFFECT_ESCALATION") verdict="REPLAY_BREAKING";
      reasons.push("ADAPTER_CHANGED:"+name);
    }
    const oldMajor=String(oldCap.version).split(".")[0],newMajor=String(next.version).split(".")[0];
    if(oldMajor!==newMajor&&verdict!=="EFFECT_ESCALATION"){
      verdict="REPLAY_BREAKING";reasons.push("CAPABILITY_MAJOR_CHANGED:"+name);
    }
  }
  const oldTools=toolMap(current.extension),newTools=toolMap(candidate.extension);
  for(const [name,oldTool] of oldTools){
    const next=newTools.get(name);
    if(!next){if(verdict==="SAFE_DROP_IN") verdict="REPLAY_BREAKING";reasons.push("TOOL_REMOVED:"+name);continue;}
    if(!schemaBackwardCompatible(oldTool.input_schema,next.input_schema)){
      if(verdict==="SAFE_DROP_IN") verdict="REPLAY_BREAKING";
      reasons.push("INPUT_SCHEMA_BREAK:"+name);
    }
  }
  if(verdict==="SAFE_DROP_IN"&&current.artifact_sha256!==candidate.artifact_sha256){
    verdict="MIGRATION_REQUIRED";
    reasons.push("IMPLEMENTATION_ARTIFACT_CHANGED");
  }
  if(verdict==="SAFE_DROP_IN"&&current.package_id!==candidate.package_id){
    reasons.push("ATTESTATION_OR_DEPENDENCY_METADATA_CHANGED");
  }
  return {
    schema:"chatgpt-web-hwpx-mcp/p3.47/compatibility/v1",
    extension_id:current.extension.extension_id,
    current_package_id:current.package_id,
    candidate_package_id:candidate.package_id,
    verdict,
    reasons,
    migration_required:verdict!=="SAFE_DROP_IN",
    shadow_required:verdict==="MIGRATION_REQUIRED",
    replay_allowed:!["REPLAY_BREAKING","EFFECT_ESCALATION","INCOMPATIBLE"].includes(verdict),
    compatibility_sha256:sha256({current_package_id:current.package_id,candidate_package_id:candidate.package_id,verdict,reasons}),
  };
}

export function compareHostConformance(observations:HostObservation[]){
  if(!Array.isArray(observations)||observations.length<2||observations.length>16) throw new Error("host conformance requires 2..16 observations");
  const rows=observations.map((x:any)=>{
    assertId(String(x.host_id||""),"host_id");
    for(const key of ["semantic_sha256","mutation_footprint_sha256","package_part_sha256"]) assertHex(String(x[key]||""),key);
    if(!Number.isInteger(x.revision_delta)||x.revision_delta<0||x.revision_delta>1) throw new Error("invalid revision_delta");
    if(x.render_observable_sha256!==undefined) assertHex(String(x.render_observable_sha256),"render_observable_sha256");
    return {
      host_id:String(x.host_id),
      semantic_sha256:String(x.semantic_sha256),
      mutation_footprint_sha256:String(x.mutation_footprint_sha256),
      revision_delta:Number(x.revision_delta),
      package_part_sha256:String(x.package_part_sha256),
      ...(x.render_observable_sha256?{render_observable_sha256:String(x.render_observable_sha256)}:{}),
    };
  }).sort((a,b)=>a.host_id.localeCompare(b.host_id));
  if(new Set(rows.map(x=>x.host_id)).size!==rows.length) throw new Error("duplicate host_id");
  const ref=rows[0];
  const dimensions=["semantic_sha256","mutation_footprint_sha256","revision_delta","package_part_sha256"] as const;
  const mismatches:any[]=[];
  for(const row of rows.slice(1)){
    for(const d of dimensions) if(row[d]!==ref[d]) mismatches.push({host_id:row.host_id,dimension:d,expected:ref[d],observed:row[d]});
  }
  const renderRows=rows.filter(x=>x.render_observable_sha256);
  let render_equal:boolean|null=null;
  if(renderRows.length>=2) render_equal=new Set(renderRows.map(x=>x.render_observable_sha256)).size===1;
  const verdict=mismatches.length===0?(render_equal===false?"SEMANTIC_EQUIVALENT_RENDER_DIVERGENCE":"PASS"):"DIVERGENT";
  return {
    schema:"chatgpt-web-hwpx-mcp/p3.47/host-conformance/v1",
    verdict,
    host_count:rows.length,
    reference_host:ref.host_id,
    mismatches,
    render_equal,
    observations:rows,
    conformance_sha256:sha256({rows,mismatches,render_equal}),
    authority:verdict==="PASS"?"DIFFERENTIAL_HOST_CONFORMANCE_PASS":"DIFFERENTIAL_HOST_CONFORMANCE_NOT_FULL_PASS",
  };
}

export function certifyPackage(rawPackage:any,catalog:any[],evidence:CertificationEvidence[],hostObservations:HostObservation[]){
  const pkg=normalizePackage(rawPackage);
  const closure=verifyDependencyClosure(rawPackage,catalog);
  const conformance=compareHostConformance(hostObservations);
  const rows=(Array.isArray(evidence)?evidence:[]).map((x:any)=>{
    if(!REQUIRED_GATES.includes(String(x.gate))) throw new Error("unknown certification gate");
    if(x.status!=="PASS"&&x.status!=="FAIL") throw new Error("invalid certification gate status");
    assertHex(String(x.evidence_sha256||""),"certification evidence sha256");
    return {gate:String(x.gate),status:x.status,evidence_sha256:String(x.evidence_sha256)};
  }).sort((a,b)=>a.gate.localeCompare(b.gate));
  const by=new Map(rows.map(x=>[x.gate,x]));
  for(const gate of REQUIRED_GATES) if(!by.has(gate)) throw new Error("missing certification gate "+gate);
  const failed=rows.filter(x=>x.status!=="PASS").map(x=>x.gate);
  if(conformance.verdict!=="PASS"&&!failed.includes("HOST_CONFORMANCE_PASS")) failed.push("HOST_CONFORMANCE_PASS");
  const status=failed.length===0?"PASS":"FAIL";
  const body={
    schema:"chatgpt-web-hwpx-mcp/p3.47/certification-certificate/v1",
    package_id:pkg.package_id,
    artifact_sha256:pkg.artifact_sha256,
    extension_id:pkg.extension.extension_id,
    extension_version:pkg.extension.version,
    dependency_closure_sha256:closure.closure_sha256,
    build_attestation_sha256:pkg.build_attestation_sha256,
    host_conformance_sha256:conformance.conformance_sha256,
    gates:rows,
    status,
    failed_gates:[...new Set(failed)].sort(),
    certificate_profile:"P347_SELF_VERIFYING_EXTENSION_V1",
  };
  const certificate_sha256=sha256(body);
  return {...body,certificate_sha256};
}

export function verifyCertificateSeal(raw:any){
  if(!raw||raw.schema!=="chatgpt-web-hwpx-mcp/p3.47/certification-certificate/v1") throw new Error("invalid certification certificate");
  const observed=String(raw.certificate_sha256||""); assertHex(observed,"certificate_sha256");
  const body={...raw}; delete body.certificate_sha256;
  const expected=sha256(body);
  if(observed!==expected) throw new Error("certification certificate seal mismatch");
  if(raw.status!=="PASS") throw new Error("certificate is not PASS");
  if(!PKG.test(String(raw.package_id||""))) throw new Error("invalid certificate package_id");
  return {ok:true,package_id:String(raw.package_id),certificate_sha256:observed,authority:"CERTIFICATE_SEAL_PASS"};
}

export function validateRolloutTransition(fromRaw:string,toRaw:string,certificate:any){
  const from=String(fromRaw) as RolloutState,to=String(toRaw) as RolloutState;
  if(!STATES.includes(from)||!STATES.includes(to)) throw new Error("invalid rollout state");
  if(!ALLOWED_TRANSITIONS[from].includes(to)) throw new Error("illegal rollout transition");
  if(["SHADOW","CANARY","PROMOTED"].includes(to)) verifyCertificateSeal(certificate);
  return {
    schema:"chatgpt-web-hwpx-mcp/p3.47/rollout-transition/v1",
    from,to,
    requires_certificate:["SHADOW","CANARY","PROMOTED"].includes(to),
    authority:"ROLLOUT_TRANSITION_GOVERNANCE_PASS",
  };
}

export const P347_SUPPLY_CHAIN_CONTRACT={
  schema:"chatgpt-web-hwpx-mcp/p3.47/supply-chain-contract/v1",
  phase:"P3.47",
  product:"0.24.0-p3.47",
  package_identity:"CONTENT_ADDRESSED_SHA256",
  provenance:{
    local_attestation_schema:"chatgpt-web-hwpx-mcp/p3.47/build-attestation/v1",
    predicate_type:"https://slsa.dev/provenance/v1",
    claim:"SLSA_INSPIRED_LOCAL_VERIFIABLE_PROFILE_NOT_EXTERNAL_SLSA_CERTIFICATION",
  },
  certification:{
    required_gates:REQUIRED_GATES,
    minimum_host_observations:2,
    certificate_seal:"SHA256_CANONICAL_JSON",
  },
  compatibility_verdicts:[
    "SAFE_DROP_IN","MIGRATION_REQUIRED","REPLAY_BREAKING","EFFECT_ESCALATION","INCOMPATIBLE"
  ],
  rollout_states:STATES,
  arbitrary_marketplace_install:false,
  arbitrary_in_process_loading:false,
  p346_sandbox_authority_preserved:true,
  p345_replay_authority_preserved:true,
  standards_inspiration:["OCI_CONTENT_ADDRESSING","IN_TOTO_ATTESTATION","SLSA_PROVENANCE","SIGSTORE_BUNDLE_MODEL"],
};

export function supplyChainContract(){return JSON.parse(JSON.stringify(P347_SUPPLY_CHAIN_CONTRACT));}

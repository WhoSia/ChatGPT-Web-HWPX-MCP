import {canonicalJson,sha256} from "./p346_capability_kernel";

export type MarketplaceEventType=
  "NAMESPACE_CLAIM"|"PUBLISH"|"YANK"|"REVOKE"|"KEY_ROTATE"|"OWNER_TRANSFER"|"CERTIFICATE_SUPERSEDE"|"POLICY_CHANGE";

const HEX64=/^[0-9a-f]{64}$/;
const PKG=/^sha256:[0-9a-f]{64}$/;
const NS=/^[a-z0-9](?:[a-z0-9.-]{0,62}[a-z0-9])?$/;
const ID=/^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}$/;
const EVENT_TYPES:MarketplaceEventType[]=[
  "NAMESPACE_CLAIM","PUBLISH","YANK","REVOKE","KEY_ROTATE","OWNER_TRANSFER","CERTIFICATE_SUPERSEDE","POLICY_CHANGE"
];
const EFFECT_RISK:Record<string,number>={
  PURE:0,READ_ONLY:0,RUNTIME_CONFIGURATION:2,DOCUMENT_MUTATION:3,EXTERNAL_WORLD_CONTACT:4,DELIVERY:5
};

function reqId(v:any,label:string):string{
  const s=String(v||"");
  if(!ID.test(s)) throw new Error("invalid "+label);
  return s;
}
function reqHex(v:any,label:string):string{
  const s=String(v||"");
  if(!HEX64.test(s)) throw new Error("invalid "+label);
  return s;
}
function reqNamespace(v:any):string{
  const s=String(v||"").toLowerCase();
  if(!NS.test(s)) throw new Error("invalid namespace");
  return s;
}
function reqTime(v:any):string{
  const s=String(v||"");
  if(!/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z$/.test(s)) throw new Error("timestamp must be RFC3339 UTC");
  return s;
}
function normalizePublisher(raw:any,withKey=false){
  if(!raw||typeof raw!=="object") throw new Error("publisher must be object");
  const out:any={
    publisher_id:reqId(raw.publisher_id,"publisher_id"),
    key_id:reqId(raw.key_id,"publisher key_id"),
    public_key_sha256:reqHex(raw.public_key_sha256,"publisher public key sha256"),
  };
  if(withKey){
    const key=String(raw.public_key_raw_base64||"");
    if(!/^[A-Za-z0-9+/]{40,48}={0,2}$/.test(key)) throw new Error("invalid publisher public key");
    out.public_key_raw_base64=key;
  }
  return out;
}
function normalizeCapabilities(raw:any){
  const rows=(Array.isArray(raw)?raw:[]).map((x:any)=>{
    if(!x||typeof x!=="object") throw new Error("capability row must be object");
    const effect=String(x.effect||"");
    if(!(effect in EFFECT_RISK)) throw new Error("invalid capability effect");
    return {name:reqId(x.name,"capability name"),version:String(x.version||"1.0.0"),effect};
  }).sort((a,b)=>a.name.localeCompare(b.name)||a.version.localeCompare(b.version));
  if(rows.length>128) throw new Error("too many capabilities");
  if(new Set(rows.map(x=>x.name)).size!==rows.length) throw new Error("duplicate capability name");
  return rows;
}
function normalizePackage(raw:any,namespace:string){
  if(!raw||typeof raw!=="object") throw new Error("publish event requires package");
  const extension_id=reqId(raw.extension_id,"extension_id");
  if(!(extension_id===namespace||extension_id.startsWith(namespace+"."))) throw new Error("extension_id is outside namespace");
  const version=String(raw.version||"");
  if(!/^\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?$/.test(version)) throw new Error("invalid extension version");
  return {
    package_id:(()=>{const p=String(raw.package_id||"");if(!PKG.test(p)) throw new Error("invalid package_id");return p;})(),
    extension_id,
    version,
    publisher_certificate_sha256:reqHex(raw.publisher_certificate_sha256,"publisher certificate sha256"),
    capabilities:normalizeCapabilities(raw.capabilities),
  };
}

export function normalizeMarketplaceEvent(raw:any){
  if(!raw||raw.schema!=="chatgpt-web-hwpx-mcp/p3.48/marketplace-event/v1") throw new Error("invalid marketplace event schema");
  const sequence=Number(raw.sequence);
  if(!Number.isInteger(sequence)||sequence<1) throw new Error("invalid event sequence");
  const event_type=String(raw.event_type||"") as MarketplaceEventType;
  if(!EVENT_TYPES.includes(event_type)) throw new Error("invalid marketplace event type");
  const namespace=reqNamespace(raw.namespace);
  const publisher=normalizePublisher(raw.publisher,event_type==="NAMESPACE_CLAIM");
  const previous_event_sha256=raw.previous_event_sha256==null?null:reqHex(raw.previous_event_sha256,"previous_event_sha256");
  if(sequence===1&&previous_event_sha256!==null) throw new Error("first event cannot have previous_event_sha256");
  if(sequence>1&&previous_event_sha256===null) throw new Error("non-first event requires previous_event_sha256");
  const base:any={
    schema:"chatgpt-web-hwpx-mcp/p3.48/marketplace-event/v1",
    sequence,event_type,timestamp:reqTime(raw.timestamp),namespace,publisher,previous_event_sha256,
  };
  if(event_type==="PUBLISH") base.package=normalizePackage(raw.package,namespace);
  if(["YANK","REVOKE","CERTIFICATE_SUPERSEDE"].includes(event_type)){
    const package_id=String(raw.package_id||"");
    if(!PKG.test(package_id)) throw new Error("invalid package_id");
    base.package_id=package_id;
  }
  if(event_type==="CERTIFICATE_SUPERSEDE"){
    base.publisher_certificate_sha256=reqHex(raw.publisher_certificate_sha256,"publisher certificate sha256");
  }
  if(event_type==="KEY_ROTATE"||event_type==="OWNER_TRANSFER"){
    base.next_publisher=normalizePublisher(raw.next_publisher,true);
    if(event_type==="KEY_ROTATE"&&base.next_publisher.publisher_id!==publisher.publisher_id) throw new Error("key rotation cannot change publisher_id");
  }
  if(event_type==="POLICY_CHANGE") base.policy_sha256=reqHex(raw.policy_sha256,"policy_sha256");
  if(["YANK","REVOKE","OWNER_TRANSFER","POLICY_CHANGE"].includes(event_type)){
    const reason=String(raw.reason||"").trim();
    if(!reason||reason.length>1000) throw new Error("event reason is required and bounded");
    base.reason=reason;
  }
  const event_sha256=sha256(base);
  if(raw.event_sha256!==undefined&&String(raw.event_sha256)!==event_sha256) throw new Error("marketplace event hash mismatch");
  return {...base,event_sha256};
}

export function reduceMarketplaceEvents(rawEvents:any[]){
  if(!Array.isArray(rawEvents)||rawEvents.length<1||rawEvents.length>10000) throw new Error("marketplace event log must contain 1..10000 events");
  const events=rawEvents.map(normalizeMarketplaceEvent);
  const owners=new Map<string,any>();
  const packages=new Map<string,any>();
  let previous:string|null=null;
  let expected=1;
  for(const e of events){
    if(e.sequence!==expected++) throw new Error("marketplace sequence gap");
    if(e.previous_event_sha256!==previous) throw new Error("marketplace hash-chain mismatch");
    const owner=owners.get(e.namespace);
    if(e.event_type==="NAMESPACE_CLAIM"){
      if(owner) throw new Error("namespace already claimed");
      owners.set(e.namespace,{...e.publisher,generation:1});
    }else{
      if(!owner) throw new Error("namespace is unclaimed");
      if(owner.publisher_id!==e.publisher.publisher_id||owner.key_id!==e.publisher.key_id||owner.public_key_sha256!==e.publisher.public_key_sha256){
        throw new Error("publisher does not own namespace at event sequence");
      }
      if(e.event_type==="PUBLISH"){
        if(packages.has(e.package.package_id)) throw new Error("package already published");
        packages.set(e.package.package_id,{...e.package,namespace:e.namespace,state:"PUBLISHED",published_sequence:e.sequence,last_event_sequence:e.sequence});
      }else if(e.event_type==="YANK"||e.event_type==="REVOKE"||e.event_type==="CERTIFICATE_SUPERSEDE"){
        const row=packages.get(e.package_id);
        if(!row||row.namespace!==e.namespace) throw new Error("package is not owned by event namespace");
        if(e.event_type==="YANK"){
          if(row.state!=="PUBLISHED") throw new Error("only published package may be yanked");
          row.state="YANKED"; row.last_event_sequence=e.sequence;
        }else if(e.event_type==="REVOKE"){
          if(row.state==="REVOKED") throw new Error("package already revoked");
          row.state="REVOKED"; row.last_event_sequence=e.sequence;
        }else{
          if(row.state==="REVOKED") throw new Error("revoked package certificate cannot be superseded");
          row.publisher_certificate_sha256=e.publisher_certificate_sha256;row.last_event_sequence=e.sequence;
        }
      }else if(e.event_type==="KEY_ROTATE"||e.event_type==="OWNER_TRANSFER"){
        owners.set(e.namespace,{...e.next_publisher,generation:Number(owner.generation||1)+1});
      }
    }
    previous=e.event_sha256;
  }
  const ownerRows=[...owners.entries()].map(([namespace,x])=>({namespace,...x})).sort((a,b)=>a.namespace.localeCompare(b.namespace));
  const packageRows=[...packages.values()].sort((a,b)=>a.package_id.localeCompare(b.package_id));
  const stateBody={owners:ownerRows,packages:packageRows,event_count:events.length,last_event_sha256:previous};
  return {
    schema:"chatgpt-web-hwpx-mcp/p3.48/marketplace-state/v1",
    ...stateBody,
    state_sha256:sha256(stateBody),
  };
}

export function discoverMarketplaceCandidates(state:any,request:any){
  if(!state||state.schema!=="chatgpt-web-hwpx-mcp/p3.48/marketplace-state/v1") throw new Error("invalid marketplace state");
  const required=(Array.isArray(request?.required_capabilities)?request.required_capabilities:[]).map((x:any)=>reqId(x,"required capability"));
  const forbidden=new Set((Array.isArray(request?.forbidden_effects)?request.forbidden_effects:[]).map(String));
  const maxEffect=request?.max_effect==null?null:String(request.max_effect);
  if(maxEffect!==null&&!(maxEffect in EFFECT_RISK)) throw new Error("invalid max_effect");
  const namespace=request?.namespace==null?null:reqNamespace(request.namespace);
  const text=String(request?.text||"").trim().toLowerCase();
  const rows=(state.packages||[]).filter((row:any)=>{
    if(row.state!=="PUBLISHED") return false;
    if(namespace&&row.namespace!==namespace) return false;
    const caps=Array.isArray(row.capabilities)?row.capabilities:[];
    const names=new Set(caps.map((x:any)=>String(x.name)));
    if(required.some((x:string)=>!names.has(x))) return false;
    if(caps.some((x:any)=>forbidden.has(String(x.effect)))) return false;
    if(maxEffect!==null&&caps.some((x:any)=>(EFFECT_RISK[String(x.effect)]??99)>EFFECT_RISK[maxEffect])) return false;
    if(text&&!String(row.extension_id).toLowerCase().includes(text)&&!caps.some((x:any)=>String(x.name).toLowerCase().includes(text))) return false;
    return true;
  }).sort((a:any,b:any)=>String(a.extension_id).localeCompare(String(b.extension_id))||String(b.version).localeCompare(String(a.version)));
  return {
    schema:"chatgpt-web-hwpx-mcp/p3.48/discovery-result/v1",
    request:{required_capabilities:required,forbidden_effects:[...forbidden].sort(),max_effect:maxEffect,namespace,text},
    candidates:rows,
    candidate_count:rows.length,
    authority:"DISCOVERY_ONLY_NOT_INSTALL_AUTHORITY",
  };
}

export const P348_MARKETPLACE_CONTRACT={
  schema:"chatgpt-web-hwpx-mcp/p3.48/marketplace-contract/v1",
  phase:"P3.48",
  product:"0.25.0-p3.48",
  principles:[
    "DISCOVERY_NOT_INSTALL_AUTHORITY",
    "REGISTRY_PRESENCE_NOT_TRUST",
    "CRYPTOGRAPHIC_NAMESPACE_CONTINUITY_NOT_REAL_WORLD_IDENTITY",
    "P347_INSTALL_TIME_RECERTIFICATION_FINAL_AUTHORITY"
  ],
  event_types:EVENT_TYPES,
  namespace_identity:"SELF_SIGNED_INITIAL_CLAIM_THEN_SIGNATURE_CONTINUITY",
  transparency:"HASH_CHAIN_PLUS_MERKLE_CHECKPOINT",
  checkpoint:"REGISTRY_SIGNATURE_PLUS_INDEPENDENT_WITNESS_QUORUM",
  federation:"SIGNED_PORTABLE_SNAPSHOT_WITH_PREFIX_OR_EQUIVOCATION_ADJUDICATION",
  discovery:"CAPABILITY_AND_EFFECT_AWARE_DESCRIPTIVE_FILTER",
  delisting:{yank:"HIDE_FROM_NORMAL_DISCOVERY",revoke:"EXECUTION_ADMISSION_BLOCK_AND_ROLLBACK_OR_RETIRE"},
  public_marketplace_install_authority:false,
  p347_install_time_recertification_required:true,
  p347_owner_scoped_trust_roots_preserved:true,
  p346_sandbox_authority_preserved:true,
};
export function marketplaceContract(){return JSON.parse(JSON.stringify(P348_MARKETPLACE_CONTRACT));}

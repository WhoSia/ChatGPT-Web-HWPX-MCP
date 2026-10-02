use serde_json::{Map,Value};
use sha2::{Digest,Sha256};

fn canonical(v:&Value)->Result<String,String>{
    match v{
        Value::Null=>Ok("null".into()),
        Value::Bool(b)=>Ok(if *b{"true"}else{"false"}.into()),
        Value::Number(n)=>Ok(n.to_string()),
        Value::String(s)=>serde_json::to_string(s).map_err(|e|e.to_string()),
        Value::Array(xs)=>{
            let mut out=String::from("[");
            for (i,x) in xs.iter().enumerate(){
                if i>0{out.push(',');}
                out.push_str(&canonical(x)?);
            }
            out.push(']');Ok(out)
        }
        Value::Object(m)=>{
            let mut keys:Vec<&String>=m.keys().collect();keys.sort();
            let mut out=String::from("{");
            for (i,k) in keys.iter().enumerate(){
                if i>0{out.push(',');}
                out.push_str(&serde_json::to_string(k).map_err(|e|e.to_string())?);
                out.push(':');out.push_str(&canonical(m.get(*k).unwrap())?);
            }
            out.push('}');Ok(out)
        }
    }
}
fn sha(v:&Value)->Result<String,String>{
    let raw=canonical(v)?;
    let mut h=Sha256::new();h.update(raw.as_bytes());
    Ok(format!("{:x}",h.finalize()))
}
fn hex64(s:&str)->bool{s.len()==64&&s.bytes().all(|b|b.is_ascii_hexdigit()&&!b.is_ascii_uppercase())}
fn pkg(s:&str)->bool{s.len()==71&&s.starts_with("sha256:")&&hex64(&s[7..])}
const REQUIRED_GATES:[&str;9]=[
    "MANIFEST_VALID","MODULE_HASH_BOUND","PROVENANCE_SUBJECT_BOUND",
    "DEPENDENCY_CLOSURE_VALID","REPRODUCIBLE_BUILD_PASS","DETERMINISM_REPLAY_PASS",
    "SANDBOX_PASS","HOST_CONFORMANCE_PASS","NEGATIVE_CONTROLS_PASS",
];

pub fn verify_certificate(v:&Value)->Result<Value,String>{
    let obj=v.as_object().ok_or("certificate must be object")?;
    if obj.get("schema").and_then(Value::as_str)!=Some("chatgpt-web-hwpx-mcp/p3.47/certification-certificate/v1"){
        return Err("invalid certificate schema".into());
    }
    if obj.get("status").and_then(Value::as_str)!=Some("PASS"){return Err("certificate is not PASS".into());}
    let package_id=obj.get("package_id").and_then(Value::as_str).ok_or("missing package_id")?;
    if !pkg(package_id){return Err("invalid package_id".into());}
    let observed=obj.get("certificate_sha256").and_then(Value::as_str).ok_or("missing certificate_sha256")?;
    if !hex64(observed){return Err("invalid certificate_sha256".into());}
    for key in ["artifact_sha256","dependency_closure_sha256","build_attestation_sha256","host_conformance_sha256"]{
        let value=obj.get(key).and_then(Value::as_str).ok_or_else(||format!("missing {key}"))?;
        if !hex64(value){return Err(format!("invalid {key}"));}
    }
    if obj.get("certificate_profile").and_then(Value::as_str)!=Some("P347_SELF_VERIFYING_EXTENSION_V2"){
        return Err("unsupported certificate profile".into());
    }
    let gates=obj.get("gates").and_then(Value::as_array).ok_or("missing gates")?;
    if gates.len()!=REQUIRED_GATES.len(){return Err("certificate gate cardinality mismatch".into());}
    let mut seen=std::collections::BTreeSet::new();
    for row in gates{
        let gate=row.get("gate").and_then(Value::as_str).ok_or("gate missing name")?;
        if !REQUIRED_GATES.contains(&gate){return Err("unknown certification gate".into());}
        if !seen.insert(gate){return Err("duplicate certification gate".into());}
        if row.get("status").and_then(Value::as_str)!=Some("PASS"){return Err("certificate gate is not PASS".into());}
        let ev=row.get("evidence_sha256").and_then(Value::as_str).ok_or("missing evidence sha256")?;
        if !hex64(ev){return Err("invalid evidence sha256".into());}
    }
    if obj.get("failed_gates").and_then(Value::as_array).map(|x|!x.is_empty()).unwrap_or(true){
        return Err("certificate failed_gates must be empty".into());
    }
    let mut body=Map::new();
    for (k,val) in obj.iter(){if k!="certificate_sha256"{body.insert(k.clone(),val.clone());}}
    let expected=sha(&Value::Object(body))?;
    if expected!=observed{return Err("certificate seal mismatch".into());}
    Ok(serde_json::json!({"ok":true,"package_id":package_id,"certificate_sha256":observed,"authority":"RUST_CERTIFICATE_SEAL_PASS"}))
}
pub fn verify_transition(v:&Value)->Result<Value,String>{
    let from=v.get("from").and_then(Value::as_str).ok_or("missing from")?;
    let to=v.get("to").and_then(Value::as_str).ok_or("missing to")?;
    let allowed=match from{
        "INSTALLED"=>vec!["CANDIDATE","RETIRED"],
        "CANDIDATE"=>vec!["SHADOW","RETIRED"],
        "SHADOW"=>vec!["CANARY","RETIRED"],
        "CANARY"=>vec!["PROMOTED","RETIRED"],
        "PROMOTED"=>vec!["RETIRED"],
        "RETIRED"=>vec![],
        _=>return Err("invalid rollout state".into()),
    };
    if !allowed.contains(&to){return Err("illegal rollout transition".into());}
    if matches!(to,"SHADOW"|"CANARY"|"PROMOTED"){
        verify_certificate(v.get("certificate").ok_or("missing certificate")?)?;
    }
    Ok(serde_json::json!({"ok":true,"from":from,"to":to,"authority":"RUST_ROLLOUT_TRANSITION_PASS"}))
}
pub fn verify_compatibility(v:&Value)->Result<Value,String>{
    let verdict=v.get("verdict").and_then(Value::as_str).ok_or("missing verdict")?;
    if !matches!(verdict,"SAFE_DROP_IN"|"MIGRATION_REQUIRED"|"REPLAY_BREAKING"|"EFFECT_ESCALATION"|"INCOMPATIBLE"){
        return Err("invalid compatibility verdict".into());
    }
    let allowed=matches!(verdict,"SAFE_DROP_IN"|"MIGRATION_REQUIRED");
    Ok(serde_json::json!({"ok":true,"verdict":verdict,"replay_admissible":allowed,"authority":"RUST_COMPATIBILITY_CLASSIFICATION_PASS"}))
}


pub fn verify_rollback(v:&Value)->Result<Value,String>{
    let current=v.get("current_certificate").ok_or("missing current certificate")?;
    let target=v.get("target_certificate").ok_or("missing target certificate")?;
    let a=verify_certificate(current)?;
    let b=verify_certificate(target)?;
    let current_id=a.get("package_id").and_then(Value::as_str).ok_or("missing current package id")?;
    let target_id=b.get("package_id").and_then(Value::as_str).ok_or("missing target package id")?;
    if current_id==target_id{return Err("rollback target must differ from current package".into());}
    Ok(serde_json::json!({
        "ok":true,
        "current_package_id":current_id,
        "target_package_id":target_id,
        "authority":"RUST_CERTIFIED_ROLLBACK_AUTHORIZATION_PASS"
    }))
}

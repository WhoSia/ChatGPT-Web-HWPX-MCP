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

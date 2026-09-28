use base64::{engine::general_purpose::STANDARD,Engine as _};
use ed25519_dalek::{Signature,Verifier,VerifyingKey};
use serde_json::{json,Map,Value};
use sha2::{Digest,Sha256};

fn canonical(v:&Value)->String{
    match v{
        Value::Null=>"null".into(),
        Value::Bool(b)=>if *b{"true".into()}else{"false".into()},
        Value::Number(n)=>n.to_string(),
        Value::String(s)=>serde_json::to_string(s).unwrap(),
        Value::Array(a)=>format!("[{}]",a.iter().map(canonical).collect::<Vec<_>>().join(",")),
        Value::Object(o)=>{
            let mut keys=o.keys().collect::<Vec<_>>();keys.sort();
            let body=keys.into_iter().map(|k|format!("{}:{}",serde_json::to_string(k).unwrap(),canonical(&o[k]))).collect::<Vec<_>>().join(",");
            format!("{{{}}}",body)
        }
    }
}
fn sha_bytes(raw:&[u8])->[u8;32]{
    let mut h=Sha256::new();h.update(raw);h.finalize().into()
}
fn sha_value(v:&Value)->String{hex::encode(sha_bytes(canonical(v).as_bytes()))}
fn hex64(s:&str)->bool{s.len()==64&&s.as_bytes().iter().all(|b|b.is_ascii_hexdigit()&&(!b.is_ascii_uppercase()))}
fn obj(v:&Value)->Result<&Map<String,Value>,String>{v.as_object().ok_or_else(||"expected object".into())}
fn field<'a>(o:&'a Map<String,Value>,k:&str)->Result<&'a Value,String>{o.get(k).ok_or_else(||format!("missing {k}"))}
fn sfield<'a>(o:&'a Map<String,Value>,k:&str)->Result<&'a str,String>{field(o,k)?.as_str().ok_or_else(||format!("{k} must be string"))}
fn key_from_record(row:&Map<String,Value>)->Result<VerifyingKey,String>{
    let raw=STANDARD.decode(sfield(row,"public_key_raw_base64")?).map_err(|_|"invalid public key base64")?;
    if raw.len()!=32{return Err("public key must be 32 bytes".into())}
    let fp=hex::encode(sha_bytes(&raw));
    if sfield(row,"public_key_sha256")?!=fp{return Err("public key fingerprint mismatch".into())}
    let arr:[u8;32]=raw.try_into().map_err(|_|"public key length")?;
    VerifyingKey::from_bytes(&arr).map_err(|e|e.to_string())
}
fn verify_signature(body:&Value,sigrow:&Map<String,Value>,root:&Map<String,Value>)->Result<(),String>{
    if sfield(sigrow,"algorithm")?!="ed25519"{return Err("unsupported signature algorithm".into())}
    if sfield(sigrow,"key_id")?!=sfield(root,"key_id")?{return Err("signature key_id mismatch".into())}
    let sigraw=STANDARD.decode(sfield(sigrow,"signature_base64")?).map_err(|_|"invalid signature base64")?;
    let sig=Signature::from_slice(&sigraw).map_err(|e|e.to_string())?;
    key_from_record(root)?.verify(canonical(body).as_bytes(),&sig).map_err(|e|e.to_string())
}
fn normalized_policy(policy:&Value)->Result<Value,String>{
    let p=obj(policy)?;
    if sfield(p,"schema")?!="chatgpt-web-hwpx-mcp/p3.48/marketplace-trust-policy/v1"{return Err("invalid trust policy schema".into())}
    let mut body=policy.clone();obj_mut(&mut body)?.remove("trust_policy_sha256");
    let observed=sfield(p,"trust_policy_sha256")?;
    if observed!=sha_value(&body){return Err("trust policy seal mismatch".into())}
    Ok(body)
}
fn obj_mut(v:&mut Value)->Result<&mut Map<String,Value>,String>{v.as_object_mut().ok_or_else(||"expected object".into())}

fn checkpoint_unsigned(cp:&Value)->Result<Value,String>{
    let mut unsigned=cp.clone();
    let o=obj_mut(&mut unsigned)?;
    o.remove("checkpoint_sha256");
    if let Some(Value::Array(rows))=o.get_mut("witness_signatures"){
        rows.sort_by(|a,b|{
            let ao=a.as_object();let bo=b.as_object();
            let ak=ao.and_then(|x|x.get("witness_id")).and_then(Value::as_str).unwrap_or("");
            let bk=bo.and_then(|x|x.get("witness_id")).and_then(Value::as_str).unwrap_or("");
            let aid=ao.and_then(|x|x.get("key_id")).and_then(Value::as_str).unwrap_or("");
            let bid=bo.and_then(|x|x.get("key_id")).and_then(Value::as_str).unwrap_or("");
            (ak,aid).cmp(&(bk,bid))
        });
    }
    Ok(unsigned)
}
pub fn verify_checkpoint(cp:&Value,policy:&Value)->Result<Value,String>{
    normalized_policy(policy)?;
    let p=obj(policy)?;let c=obj(cp)?;
    if sfield(c,"schema")?!="chatgpt-web-hwpx-mcp/p3.48/marketplace-checkpoint/v1"{return Err("invalid checkpoint schema".into())}
    let body=field(c,"body")?;
    let registry=obj(field(p,"registry")?)?;
    let rs=obj(field(c,"registry_signature")?)?;
    if sfield(rs,"registry_id")?!=sfield(registry,"registry_id")?{return Err("registry id mismatch".into())}
    verify_signature(body,rs,registry)?;
    let witnesses=field(p,"witnesses")?.as_array().ok_or("witnesses must be array")?;
    let mut roots=std::collections::HashMap::new();
    for row in witnesses{
        let ro=obj(row)?;
        roots.insert((sfield(ro,"witness_id")?.to_owned(),sfield(ro,"key_id")?.to_owned()),ro);
    }
    let minimum=field(p,"minimum_witnesses")?.as_u64().ok_or("minimum_witnesses must be integer")? as usize;
    let sigs=field(c,"witness_signatures")?.as_array().ok_or("witness signatures must be array")?;
    let mut seen=std::collections::HashSet::new();
    let mut accepted=0usize;
    for row in sigs{
        let so=obj(row)?;
        let key=(sfield(so,"witness_id")?.to_owned(),sfield(so,"key_id")?.to_owned());
        if seen.contains(&key){continue}
        if let Some(root)=roots.get(&key){
            if verify_signature(body,so,root).is_ok(){seen.insert(key);accepted+=1;}
        }
    }
    if accepted<minimum{return Err("witness quorum not met".into())}
    let observed=sfield(c,"checkpoint_sha256")?;
    let unsigned=checkpoint_unsigned(cp)?;
    if observed!=sha_value(&unsigned){return Err("checkpoint seal mismatch".into())}
    Ok(json!({"ok":true,"checkpoint_sha256":observed,"accepted_witnesses":accepted,"authority":"RUST_REGISTRY_WITNESS_CHECKPOINT_PASS"}))
}

fn verify_event_hashes(events:&[Value])->Result<Vec<String>,String>{
    let mut hashes=Vec::with_capacity(events.len());
    let mut prev:Option<String>=None;
    for (i,row) in events.iter().enumerate(){
        let o=obj(row)?;
        let seq=field(o,"sequence")?.as_u64().ok_or("sequence must be integer")? as usize;
        if seq!=i+1{return Err("event sequence gap".into())}
        let observed=sfield(o,"event_sha256")?;
        if !hex64(observed){return Err("invalid event hash".into())}
        match (&prev,o.get("previous_event_sha256")){
            (None,Some(Value::Null))=>{},
            (Some(p),Some(Value::String(s))) if s==p=>{},
            _=>return Err("event hash chain mismatch".into()),
        }
        let mut body=row.clone();
        let bo=obj_mut(&mut body)?;
        bo.remove("verification");bo.remove("event_sha256");
        if observed!=sha_value(&body){return Err("event seal mismatch".into())}
        hashes.push(observed.to_owned());prev=Some(observed.to_owned());
    }
    Ok(hashes)
}
fn merkle_root(hashes:&[String])->Result<String,String>{
    if hashes.is_empty(){return Ok(hex::encode(sha_bytes(b"")))}
    let mut level=Vec::<[u8;32]>::new();
    for h in hashes{
        let raw=hex::decode(h).map_err(|_|"invalid event hash hex")?;
        let mut leaf=Vec::with_capacity(33);leaf.push(0);leaf.extend_from_slice(&raw);
        level.push(sha_bytes(&leaf));
    }
    while level.len()>1{
        let mut next=Vec::new();
        for i in (0..level.len()).step_by(2){
            let left=level[i];let right=if i+1<level.len(){level[i+1]}else{left};
            let mut node=Vec::with_capacity(65);node.push(1);node.extend_from_slice(&left);node.extend_from_slice(&right);
            next.push(sha_bytes(&node));
        }
        level=next;
    }
    Ok(hex::encode(level[0]))
}
fn package_state(events:&[Value],target:&str)->Result<String,String>{
    let mut state="ABSENT".to_string();
    for e in events{
        let o=obj(e)?;let kind=sfield(o,"event_type")?;
        if kind=="PUBLISH"{
            let po=obj(field(o,"package")?)?;
            if sfield(po,"package_id")?==target{state="PUBLISHED".into();}
        }else if ["YANK","REVOKE"].contains(&kind){
            if o.get("package_id").and_then(Value::as_str)==Some(target){
                state=if kind=="YANK"{"YANKED".into()}else{"REVOKED".into()};
            }
        }
    }
    Ok(state)
}
pub fn verify_bundle(v:&Value)->Result<Value,String>{
    let o=obj(v)?;
    if sfield(o,"schema")?!="chatgpt-web-hwpx-mcp/p3.48/offline-marketplace-bundle/v1"{return Err("invalid bundle schema".into())}
    let policy=field(o,"trust_policy")?;
    normalized_policy(policy)?;
    let snapshot=obj(field(o,"snapshot")?)?;
    if sfield(snapshot,"schema")?!="chatgpt-web-hwpx-mcp/p3.48/marketplace-snapshot/v1"{return Err("invalid snapshot schema".into())}
    let events=field(snapshot,"events")?.as_array().ok_or("events must be array")?;
    if events.is_empty(){return Err("snapshot must not be empty".into())}
    let hashes=verify_event_hashes(events)?;
    let checkpoint=field(snapshot,"checkpoint")?;
    let cp_receipt=verify_checkpoint(checkpoint,policy)?;
    let body=obj(field(obj(checkpoint)?,"body")?)?;
    if field(body,"event_count")?.as_u64()!=Some(events.len() as u64){return Err("checkpoint event_count mismatch".into())}
    if sfield(body,"last_event_sha256")?!=hashes.last().unwrap(){return Err("checkpoint last event mismatch".into())}
    if sfield(body,"merkle_root")?!=merkle_root(&hashes)?{return Err("checkpoint merkle root mismatch".into())}
    let target=sfield(o,"package_id")?;
    if !target.starts_with("sha256:")||target.len()!=71{return Err("invalid bundle package_id".into())}
    let state=package_state(events,target)?;
    if state!="PUBLISHED"{return Err(format!("bundle package state is {state}"))}
    let mut body_bundle=v.clone();
    let bo=obj_mut(&mut body_bundle)?;bo.remove("bundle_sha256");bo.remove("rust_receipt");
    let observed=sfield(o,"bundle_sha256")?;
    if observed!=sha_value(&body_bundle){return Err("bundle seal mismatch".into())}
    Ok(json!({"ok":true,"package_id":target,"event_count":events.len(),"merkle_root":sfield(body,"merkle_root")?,"checkpoint":cp_receipt,"authority":"RUST_OFFLINE_MARKETPLACE_BUNDLE_PASS"}))
}

#[cfg(test)]
mod tests{
    use super::*;
    #[test] fn canonical_is_key_sorted(){
        let a=json!({"b":1,"a":2});let b=json!({"a":2,"b":1});
        assert_eq!(canonical(&a),canonical(&b));assert_eq!(sha_value(&a),sha_value(&b));
    }
}

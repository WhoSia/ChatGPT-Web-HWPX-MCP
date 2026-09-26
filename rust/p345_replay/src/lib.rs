use serde_json::{Map, Value};
use sha2::{Digest,Sha256};
use std::collections::{BTreeMap,BTreeSet};

fn canonical(v:&Value)->Result<String,String>{
    match v {
        Value::Null=>Ok("null".into()),
        Value::Bool(b)=>Ok(if *b{"true"}else{"false"}.into()),
        Value::Number(n)=>{
            if let Some(i)=n.as_i64(){Ok(i.to_string())}
            else if let Some(u)=n.as_u64(){Ok(u.to_string())}
            else{Err("deterministic payload forbids floats".into())}
        },
        Value::String(s)=>serde_json::to_string(s).map_err(|e|e.to_string()),
        Value::Array(a)=>{
            let mut out=Vec::with_capacity(a.len());
            for x in a{out.push(canonical(x)?);}
            Ok(format!("[{}]",out.join(",")))
        },
        Value::Object(o)=>{
            let mut keys:Vec<&String>=o.keys().collect();keys.sort();
            let mut out=Vec::with_capacity(keys.len());
            for k in keys{out.push(format!("{}:{}",serde_json::to_string(k).unwrap(),canonical(&o[k])?));}
            Ok(format!("{{{}}}",out.join(",")))
        }
    }
}
fn hex(bytes:&[u8])->String{bytes.iter().map(|b|format!("{:02x}",b)).collect()}
pub fn event_hash(previous:&str,seq:u64,body:&Value)->Result<String,String>{
    let mut h=Sha256::new();
    h.update(b"p3.45-event-v1\0");h.update(previous.as_bytes());h.update(b"\0");h.update(seq.to_string().as_bytes());h.update(b"\0");h.update(canonical(body)?.as_bytes());
    Ok(hex(&h.finalize()))
}
fn terminal(s:&str)->bool{matches!(s,"COMMITTED"|"REUSED")}
pub fn verify_state(state:&Value)->Result<Value,String>{
    let obj=state.as_object().ok_or("state must be object")?;
    if obj.get("schema").and_then(Value::as_str)!=Some("chatgpt-web-hwpx-mcp/p3.45/runtime-run/v1"){return Err("invalid runtime schema".into());}
    let compiled=obj.get("compiled").and_then(Value::as_object).ok_or("compiled missing")?;
    let order=compiled.get("topological_order").and_then(Value::as_array).ok_or("topological_order missing")?;
    let actions=compiled.get("actions").and_then(Value::as_object).ok_or("actions missing")?;
    let ir=compiled.get("ir").and_then(Value::as_object).ok_or("ir missing")?;
    let nodes=ir.get("nodes").and_then(Value::as_array).ok_or("nodes missing")?;
    let mut deps:BTreeMap<String,Vec<String>>=BTreeMap::new();
    for n in nodes{
        let o=n.as_object().ok_or("node must be object")?;
        let id=o.get("id").and_then(Value::as_str).ok_or("node id missing")?.to_string();
        let ds=o.get("deps").and_then(Value::as_array).cloned().unwrap_or_default().iter().map(|x|x.as_str().unwrap_or("").to_string()).collect();
        deps.insert(id,ds);
    }
    let mut states:BTreeMap<String,String>=BTreeMap::new();
    for id in order{states.insert(id.as_str().ok_or("bad node id")?.to_string(),"PENDING".into());}
    let events=obj.get("events").and_then(Value::as_array).ok_or("events missing")?;
    let mut previous="GENESIS".to_string();let mut seen_seq=0u64;let mut completed=false;
    for raw in events{
        let e=raw.as_object().ok_or("event must be object")?;
        let seq=e.get("seq").and_then(Value::as_u64).ok_or("event seq missing")?;
        if seq!=seen_seq+1{return Err("event sequence gap".into());}
        if e.get("previous_event_hash").and_then(Value::as_str)!=Some(previous.as_str()){return Err("previous event hash mismatch".into());}
        let mut body=Map::new();
        for key in ["name","run_id","node_id","revision","attributes"]{if let Some(v)=e.get(key){body.insert(key.to_string(),v.clone());}}
        let expected=event_hash(&previous,seq,&Value::Object(body))?;
        if e.get("event_hash").and_then(Value::as_str)!=Some(expected.as_str()){return Err("event hash mismatch".into());}
        let name=e.get("name").and_then(Value::as_str).ok_or("event name missing")?;
        let node=e.get("node_id").and_then(Value::as_str);
        if let Some(id)=node{
            let current=states.get(id).cloned().ok_or("event references unknown node")?;
            let ready=deps.get(id).cloned().unwrap_or_default().iter().all(|d|states.get(d).map(|s|terminal(s)).unwrap_or(false));
            match name{
                "NODE_REUSED"=>{if current!="PENDING"||actions.get(id).and_then(Value::as_str)!=Some("REUSE")||!ready{return Err("invalid NODE_REUSED transition".into());}states.insert(id.into(),"REUSED".into());},
                "NODE_STARTED"=>{if current!="PENDING"||actions.get(id).and_then(Value::as_str)!=Some("EXECUTE")||!ready{return Err("invalid NODE_STARTED transition".into());}states.insert(id.into(),"RUNNING".into());},
                "NODE_WAITING_EXTERNAL"=>{if current!="PENDING"||actions.get(id).and_then(Value::as_str)!=Some("WAIT_EXTERNAL")||!ready{return Err("invalid NODE_WAITING_EXTERNAL transition".into());}states.insert(id.into(),"WAITING_EXTERNAL".into());},
                "NODE_COMMITTED"=>{if !matches!(current.as_str(),"RUNNING"|"WAITING_EXTERNAL"){return Err("invalid NODE_COMMITTED transition".into());}states.insert(id.into(),"COMMITTED".into());},
                "NODE_FAILED"=>{if !matches!(current.as_str(),"RUNNING"|"WAITING_EXTERNAL"){return Err("invalid NODE_FAILED transition".into());}states.insert(id.into(),"FAILED".into());},
                _=>{}
            }
        }
        if name=="RUN_COMPLETED"{if states.values().any(|s|!terminal(s)){return Err("run completed with nonterminal nodes".into());}completed=true;}
        previous=expected;seen_seq=seq;
    }
    if obj.get("head_event_hash").and_then(Value::as_str)!=Some(previous.as_str()){return Err("head event hash mismatch".into());}
    let mut counts:BTreeMap<String,u64>=BTreeMap::new();
    for s in states.values(){*counts.entry(s.clone()).or_insert(0)+=1;}
    Ok(serde_json::json!({"ok":true,"event_count":events.len(),"head_event_hash":previous,"node_state_counts":counts,"completed":completed,"authority":"RUST_DETERMINISTIC_REPLAY_INVARIANT_PASS"}))
}

#[cfg(test)]
mod tests{
 use super::*;
 #[test]fn integer_canonical_hash_stable(){let b=serde_json::json!({"name":"RUN_CREATED","run_id":"r","revision":1,"attributes":{"b":2,"a":1}});assert_eq!(event_hash("GENESIS",1,&b).unwrap(),event_hash("GENESIS",1,&serde_json::json!({"attributes":{"a":1,"b":2},"revision":1,"run_id":"r","name":"RUN_CREATED"})).unwrap());}
 #[test]fn float_rejected(){assert!(event_hash("GENESIS",1,&serde_json::json!({"x":1.5})).is_err());}
}

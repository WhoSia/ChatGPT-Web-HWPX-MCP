use serde_json::Value;
use std::collections::{BTreeMap,BTreeSet,VecDeque};

const EFFECTS:[&str;6]=["READ_ONLY","PURE","DOCUMENT_MUTATION","RUNTIME_CONFIGURATION","EXTERNAL_WORLD_CONTACT","DELIVERY"];

fn known_effect(e:&str)->bool{EFFECTS.contains(&e)}
fn expected_actions(effect:&str,reusable:bool)->&'static [&'static str]{
    match effect{
        "EXTERNAL_WORLD_CONTACT"=>&["WAIT_EXTERNAL"],
        "READ_ONLY"|"PURE" if reusable=>&["EXECUTE","REUSE"],
        _=>&["EXECUTE"],
    }
}

pub fn verify_effect_plan(value:&Value)->Result<Value,String>{
    let obj=value.as_object().ok_or("plan must be object")?;
    if obj.get("schema").and_then(Value::as_str)!=Some("chatgpt-web-hwpx-mcp/p3.46/effect-plan/v1"){
        return Err("invalid P3.46 effect plan schema".into());
    }
    let nodes=obj.get("nodes").and_then(Value::as_array).ok_or("nodes missing")?;
    if nodes.is_empty()||nodes.len()>128{return Err("effect plan requires 1..128 nodes".into());}

    let mut rows:BTreeMap<String,(Vec<String>,String,String,bool)>=BTreeMap::new();
    let mut indegree:BTreeMap<String,usize>=BTreeMap::new();
    let mut children:BTreeMap<String,Vec<String>>=BTreeMap::new();

    for raw in nodes{
        let o=raw.as_object().ok_or("node must be object")?;
        let id=o.get("id").and_then(Value::as_str).ok_or("node id missing")?.to_string();
        if id.is_empty()||rows.contains_key(&id){return Err("duplicate/empty node id".into());}
        let effect=o.get("effect").and_then(Value::as_str).ok_or("effect missing")?.to_string();
        if !known_effect(&effect){return Err(format!("invalid effect at {id}"));}
        let action=o.get("action").and_then(Value::as_str).unwrap_or("EXECUTE").to_string();
        let reusable=o.get("reusable").and_then(Value::as_bool).unwrap_or(false);
        if reusable&&!matches!(effect.as_str(),"READ_ONLY"|"PURE"){return Err("only READ_ONLY/PURE may be reusable".into());}
        if !expected_actions(&effect,reusable).contains(&action.as_str()){return Err(format!("action/effect mismatch at {id}"));}
        let deps=o.get("deps").and_then(Value::as_array).cloned().unwrap_or_default()
            .into_iter().map(|x|x.as_str().unwrap_or("").to_string()).collect::<Vec<_>>();
        let unique:BTreeSet<_>=deps.iter().collect();
        if unique.len()!=deps.len(){return Err("duplicate dependency".into());}
        indegree.insert(id.clone(),0);
        children.insert(id.clone(),Vec::new());
        rows.insert(id,(deps,effect,action,reusable));
    }

    for (id,(deps,_,_,_)) in &rows{
        for dep in deps{
            if !rows.contains_key(dep){return Err(format!("unknown dependency {dep}"));}
            *indegree.get_mut(id).unwrap()+=1;
            children.get_mut(dep).unwrap().push(id.clone());
        }
    }
    for (id,(_,effect,_,_)) in &rows{
        if effect=="DELIVERY"&&!children.get(id).unwrap().is_empty(){
            return Err("DELIVERY must be a terminal DAG sink".into());
        }
    }

    let mut q:VecDeque<String>=indegree.iter().filter(|(_,v)|**v==0).map(|(k,_)|k.clone()).collect();
    let mut order=Vec::new();
    while !q.is_empty(){
        let mut ready=q.drain(..).collect::<Vec<_>>();
        ready.sort();
        for id in ready{
            order.push(id.clone());
            let mut cs=children.get(&id).cloned().unwrap_or_default();
            cs.sort();
            for c in cs{
                let d=indegree.get_mut(&c).unwrap();
                *d-=1;
                if *d==0{q.push_back(c);}
            }
        }
    }
    if order.len()!=rows.len(){return Err("effect plan contains cycle".into());}

    Ok(serde_json::json!({
        "ok":true,
        "schema":"chatgpt-web-hwpx-mcp/p3.46/rust-effect-verification/v1",
        "topological_order":order,
        "node_count":rows.len(),
        "authority":"RUST_EFFECT_PLAN_INVARIANT_PASS"
    }))
}

pub fn verify_tool_sequence(value:&Value)->Result<Value,String>{
    let rows=value.get("effects").and_then(Value::as_array).ok_or("effects missing")?;
    if rows.is_empty()||rows.len()>128{return Err("sequence requires 1..128 effects".into());}
    let mut delivery=None;
    for (i,v) in rows.iter().enumerate(){
        let e=v.as_str().ok_or("effect must be string")?;
        if !known_effect(e){return Err("invalid effect".into());}
        if e=="DELIVERY"{
            if delivery.is_some(){return Err("at most one DELIVERY is allowed".into());}
            delivery=Some(i);
        }
    }
    if let Some(i)=delivery{
        if i+1!=rows.len(){return Err("DELIVERY must terminate sequence".into());}
    }
    Ok(serde_json::json!({
        "ok":true,
        "count":rows.len(),
        "authority":"RUST_TOOL_SEQUENCE_INVARIANT_PASS"
    }))
}

#[cfg(test)]
mod tests{
    use super::*;

    #[test]
    fn valid_plan(){
        let v=serde_json::json!({
            "schema":"chatgpt-web-hwpx-mcp/p3.46/effect-plan/v1",
            "nodes":[
                {"id":"a","deps":[],"effect":"READ_ONLY","action":"REUSE","reusable":true},
                {"id":"b","deps":["a"],"effect":"DOCUMENT_MUTATION","action":"EXECUTE"},
                {"id":"c","deps":["b"],"effect":"DELIVERY","action":"EXECUTE"}
            ]
        });
        assert!(verify_effect_plan(&v).is_ok());
    }

    #[test]
    fn rejects_delivery_parent(){
        let v=serde_json::json!({
            "schema":"chatgpt-web-hwpx-mcp/p3.46/effect-plan/v1",
            "nodes":[
                {"id":"d","effect":"DELIVERY"},
                {"id":"x","deps":["d"],"effect":"PURE"}
            ]
        });
        assert!(verify_effect_plan(&v).is_err());
    }

    #[test]
    fn rejects_reusable_mutation(){
        let v=serde_json::json!({
            "schema":"chatgpt-web-hwpx-mcp/p3.46/effect-plan/v1",
            "nodes":[{"id":"x","effect":"DOCUMENT_MUTATION","reusable":true}]
        });
        assert!(verify_effect_plan(&v).is_err());
    }

    #[test]
    fn sequence_terminal_delivery(){
        assert!(verify_tool_sequence(&serde_json::json!({"effects":["READ_ONLY","DOCUMENT_MUTATION","DELIVERY"]})).is_ok());
        assert!(verify_tool_sequence(&serde_json::json!({"effects":["DELIVERY","READ_ONLY"]})).is_err());
    }
}

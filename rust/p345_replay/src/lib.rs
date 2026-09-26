use serde_json::{Map, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};

fn canonical(v: &Value) -> Result<String, String> {
    match v {
        Value::Null => Ok("null".into()),
        Value::Bool(b) => Ok(if *b { "true" } else { "false" }.into()),
        Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                Ok(i.to_string())
            } else if let Some(u) = n.as_u64() {
                Ok(u.to_string())
            } else {
                Err("deterministic payload forbids floats".into())
            }
        }
        Value::String(s) => serde_json::to_string(s).map_err(|e| e.to_string()),
        Value::Array(a) => {
            let mut out = Vec::with_capacity(a.len());
            for x in a {
                out.push(canonical(x)?);
            }
            Ok(format!("[{}]", out.join(",")))
        }
        Value::Object(o) => {
            let mut keys: Vec<&String> = o.keys().collect();
            keys.sort();
            let mut out = Vec::with_capacity(keys.len());
            for k in keys {
                out.push(format!(
                    "{}:{}",
                    serde_json::to_string(k).unwrap(),
                    canonical(&o[k])?
                ));
            }
            Ok(format!("{{{}}}", out.join(",")))
        }
    }
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{:02x}", b)).collect()
}

fn sha64(value: &str) -> bool {
    value.len() == 64 && value.bytes().all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
}

pub fn event_hash(previous: &str, seq: u64, body: &Value) -> Result<String, String> {
    let mut h = Sha256::new();
    h.update(b"p3.45-event-v1\0");
    h.update(previous.as_bytes());
    h.update(b"\0");
    h.update(seq.to_string().as_bytes());
    h.update(b"\0");
    h.update(canonical(body)?.as_bytes());
    Ok(hex(&h.finalize()))
}

fn terminal(s: &str) -> bool {
    matches!(s, "COMMITTED" | "REUSED")
}

fn attr_str<'a>(event: &'a Map<String, Value>, key: &str) -> Result<&'a str, String> {
    event
        .get("attributes")
        .and_then(Value::as_object)
        .and_then(|m| m.get(key))
        .and_then(Value::as_str)
        .ok_or_else(|| format!("missing event attribute {key}"))
}

pub fn verify_state(state: &Value) -> Result<Value, String> {
    let obj = state.as_object().ok_or("state must be object")?;
    if obj.get("schema").and_then(Value::as_str)
        != Some("chatgpt-web-hwpx-mcp/p3.45/runtime-run/v1")
    {
        return Err("invalid runtime schema".into());
    }
    let run_id = obj
        .get("run_id")
        .and_then(Value::as_str)
        .ok_or("run_id missing")?;
    let base_revision = obj
        .get("base_revision")
        .and_then(Value::as_u64)
        .ok_or("base_revision missing")?;
    let compiled = obj
        .get("compiled")
        .and_then(Value::as_object)
        .ok_or("compiled missing")?;
    let order = compiled
        .get("topological_order")
        .and_then(Value::as_array)
        .ok_or("topological_order missing")?;
    let actions = compiled
        .get("actions")
        .and_then(Value::as_object)
        .ok_or("actions missing")?;
    let side_effects = compiled
        .get("side_effects")
        .and_then(Value::as_object)
        .ok_or("side_effects missing")?;
    let ir = compiled
        .get("ir")
        .and_then(Value::as_object)
        .ok_or("ir missing")?;
    let nodes = ir
        .get("nodes")
        .and_then(Value::as_array)
        .ok_or("nodes missing")?;

    let order_ids: Vec<String> = order
        .iter()
        .map(|v| v.as_str().ok_or("bad node id").map(str::to_string))
        .collect::<Result<_, _>>()?;
    let unique: BTreeSet<String> = order_ids.iter().cloned().collect();
    if unique.len() != order_ids.len() || unique.len() != nodes.len() {
        return Err("topological order is not a unique full node inventory".into());
    }
    let position: BTreeMap<String, usize> = order_ids
        .iter()
        .enumerate()
        .map(|(i, id)| (id.clone(), i))
        .collect();

    let mut deps: BTreeMap<String, Vec<String>> = BTreeMap::new();
    for n in nodes {
        let o = n.as_object().ok_or("node must be object")?;
        let id = o
            .get("id")
            .and_then(Value::as_str)
            .ok_or("node id missing")?
            .to_string();
        if deps.contains_key(&id) || !position.contains_key(&id) {
            return Err("node inventory/order mismatch".into());
        }
        let ds: Vec<String> = o
            .get("deps")
            .and_then(Value::as_array)
            .cloned()
            .unwrap_or_default()
            .iter()
            .map(|x| x.as_str().unwrap_or("").to_string())
            .collect();
        for dep in &ds {
            let dp = *position.get(dep).ok_or("dependency references unknown node")?;
            let np = *position.get(&id).ok_or("node missing from order")?;
            if dp >= np {
                return Err("topological order violates dependency order".into());
            }
        }
        deps.insert(id, ds);
    }

    for id in &order_ids {
        let action = actions
            .get(id)
            .and_then(Value::as_str)
            .ok_or("node action missing")?;
        let effect = side_effects
            .get(id)
            .and_then(Value::as_str)
            .ok_or("node side effect missing")?;
        match (action, effect) {
            ("REUSE", "PURE") => {}
            ("EXECUTE", "PURE" | "DOCUMENT_MUTATION") => {}
            ("WAIT_EXTERNAL", "EXTERNAL_WORLD_CONTACT") => {}
            _ => return Err("action/side-effect contract mismatch".into()),
        }
    }

    let mut states: BTreeMap<String, String> = order_ids
        .iter()
        .map(|id| (id.clone(), "PENDING".into()))
        .collect();
    let mut outputs: BTreeMap<String, (String, Option<String>)> = BTreeMap::new();
    let events = obj
        .get("events")
        .and_then(Value::as_array)
        .ok_or("events missing")?;
    if events.is_empty() {
        return Err("runtime must contain RUN_CREATED".into());
    }

    let mut previous = "GENESIS".to_string();
    let mut seen_seq = 0u64;
    let mut current_revision = base_revision;
    let mut status = "READY".to_string();
    let mut terminal_run = false;

    for raw in events {
        if terminal_run {
            return Err("event appears after terminal run event".into());
        }
        let e = raw.as_object().ok_or("event must be object")?;
        let seq = e
            .get("seq")
            .and_then(Value::as_u64)
            .ok_or("event seq missing")?;
        if seq != seen_seq + 1 {
            return Err("event sequence gap".into());
        }
        if e.get("previous_event_hash").and_then(Value::as_str) != Some(previous.as_str()) {
            return Err("previous event hash mismatch".into());
        }
        if e.get("run_id").and_then(Value::as_str) != Some(run_id) {
            return Err("event run_id mismatch".into());
        }

        let mut body = Map::new();
        for key in ["name", "run_id", "node_id", "revision", "attributes"] {
            if let Some(v) = e.get(key) {
                body.insert(key.to_string(), v.clone());
            }
        }
        let expected = event_hash(&previous, seq, &Value::Object(body))?;
        if e.get("event_hash").and_then(Value::as_str) != Some(expected.as_str()) {
            return Err("event hash mismatch".into());
        }

        let name = e
            .get("name")
            .and_then(Value::as_str)
            .ok_or("event name missing")?;
        let revision = e
            .get("revision")
            .and_then(Value::as_u64)
            .ok_or("event revision missing")?;
        let node = e.get("node_id").and_then(Value::as_str);

        if seq == 1 {
            if name != "RUN_CREATED" || node.is_some() || revision != base_revision {
                return Err("first event must be base-revision RUN_CREATED".into());
            }
        } else if name == "RUN_CREATED" {
            return Err("RUN_CREATED may occur only once".into());
        }

        if let Some(id) = node {
            let current = states
                .get(id)
                .cloned()
                .ok_or("event references unknown node")?;
            let ready = deps
                .get(id)
                .cloned()
                .unwrap_or_default()
                .iter()
                .all(|d| states.get(d).map(|s| terminal(s)).unwrap_or(false));
            if !ready {
                return Err("node event occurred before dependencies were terminal".into());
            }
            let action = actions.get(id).and_then(Value::as_str).unwrap_or("");
            let effect = side_effects.get(id).and_then(Value::as_str).unwrap_or("");
            match name {
                "NODE_REUSED" => {
                    if current != "PENDING" || action != "REUSE" || revision != current_revision {
                        return Err("invalid NODE_REUSED transition".into());
                    }
                    let output = attr_str(e, "output_sha256")?;
                    if !sha64(output) {
                        return Err("invalid reused output sha256".into());
                    }
                    states.insert(id.into(), "REUSED".into());
                    outputs.insert(id.into(), (output.into(), None));
                }
                "NODE_STARTED" => {
                    if current != "PENDING"
                        || action != "EXECUTE"
                        || effect == "EXTERNAL_WORLD_CONTACT"
                        || revision != current_revision
                    {
                        return Err("invalid NODE_STARTED transition".into());
                    }
                    states.insert(id.into(), "RUNNING".into());
                    status = "RUNNING".into();
                }
                "NODE_WAITING_EXTERNAL" => {
                    if current != "PENDING"
                        || action != "WAIT_EXTERNAL"
                        || effect != "EXTERNAL_WORLD_CONTACT"
                        || revision != current_revision
                    {
                        return Err("invalid NODE_WAITING_EXTERNAL transition".into());
                    }
                    states.insert(id.into(), "WAITING_EXTERNAL".into());
                    status = "WAIT_EXTERNAL".into();
                }
                "NODE_COMMITTED" => {
                    if !matches!(current.as_str(), "RUNNING" | "WAITING_EXTERNAL") {
                        return Err("invalid NODE_COMMITTED transition".into());
                    }
                    let expected_revision = if current == "WAITING_EXTERNAL" {
                        if effect != "EXTERNAL_WORLD_CONTACT" {
                            return Err("waiting node has non-external side effect".into());
                        }
                        current_revision
                    } else if effect == "DOCUMENT_MUTATION" {
                        current_revision + 1
                    } else if effect == "PURE" {
                        current_revision
                    } else {
                        return Err("started node has invalid side effect".into());
                    };
                    if revision != expected_revision {
                        return Err("committed revision violates side-effect contract".into());
                    }
                    let output = attr_str(e, "output_sha256")?;
                    let receipt = attr_str(e, "receipt_sha256")?;
                    if !sha64(output) || !sha64(receipt) {
                        return Err("invalid committed output/receipt sha256".into());
                    }
                    states.insert(id.into(), "COMMITTED".into());
                    outputs.insert(id.into(), (output.into(), Some(receipt.into())));
                    current_revision = revision;
                    status = "RUNNING".into();
                }
                "NODE_FAILED" => {
                    if !matches!(current.as_str(), "RUNNING" | "WAITING_EXTERNAL")
                        || revision != current_revision
                    {
                        return Err("invalid NODE_FAILED transition".into());
                    }
                    states.insert(id.into(), "FAILED".into());
                    status = "HOLD".into();
                }
                _ => return Err("node event uses unsupported event name".into()),
            }
        } else {
            match name {
                "RUN_CREATED" => {}
                "RUN_COMPLETED" => {
                    if revision != current_revision || states.values().any(|s| !terminal(s)) {
                        return Err("invalid RUN_COMPLETED transition".into());
                    }
                    status = "COMPLETED".into();
                    terminal_run = true;
                }
                "RUN_ABORTED" => {
                    if revision != current_revision {
                        return Err("invalid RUN_ABORTED revision".into());
                    }
                    status = "ABORTED".into();
                    terminal_run = true;
                }
                _ => return Err("run event uses unsupported event name".into()),
            }
        }

        previous = expected;
        seen_seq = seq;
    }

    if obj.get("head_event_hash").and_then(Value::as_str) != Some(previous.as_str()) {
        return Err("head event hash mismatch".into());
    }
    if obj.get("current_revision").and_then(Value::as_u64) != Some(current_revision) {
        return Err("materialized current_revision diverges from replay".into());
    }
    if obj.get("status").and_then(Value::as_str) != Some(status.as_str()) {
        return Err("materialized run status diverges from replay".into());
    }

    let material_states = obj
        .get("node_states")
        .and_then(Value::as_object)
        .ok_or("materialized node_states missing")?;
    if material_states.len() != states.len() {
        return Err("materialized node_states inventory mismatch".into());
    }
    for (id, expected_state) in &states {
        if material_states.get(id).and_then(Value::as_str) != Some(expected_state.as_str()) {
            return Err(format!("materialized node state mismatch: {id}"));
        }
    }

    let material_outputs = obj
        .get("outputs")
        .and_then(Value::as_object)
        .ok_or("materialized outputs missing")?;
    for (id, (output, receipt)) in &outputs {
        let row = material_outputs
            .get(id)
            .and_then(Value::as_object)
            .ok_or_else(|| format!("materialized output missing: {id}"))?;
        if row.get("output_sha256").and_then(Value::as_str) != Some(output.as_str()) {
            return Err(format!("materialized output hash mismatch: {id}"));
        }
        if let Some(receipt) = receipt {
            if row.get("receipt_sha256").and_then(Value::as_str) != Some(receipt.as_str()) {
                return Err(format!("materialized receipt hash mismatch: {id}"));
            }
        }
    }

    let mut counts: BTreeMap<String, u64> = BTreeMap::new();
    for s in states.values() {
        *counts.entry(s.clone()).or_insert(0) += 1;
    }
    Ok(serde_json::json!({
        "ok": true,
        "event_count": events.len(),
        "head_event_hash": previous,
        "current_revision": current_revision,
        "status": status,
        "node_state_counts": counts,
        "completed": status == "COMPLETED",
        "aborted": status == "ABORTED",
        "authority": "RUST_DETERMINISTIC_REPLAY_AND_MATERIALIZED_STATE_INVARIANT_PASS"
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn integer_canonical_hash_stable() {
        let b = serde_json::json!({
            "name":"RUN_CREATED",
            "run_id":"r",
            "revision":1,
            "attributes":{"b":2,"a":1}
        });
        assert_eq!(
            event_hash("GENESIS", 1, &b).unwrap(),
            event_hash(
                "GENESIS",
                1,
                &serde_json::json!({
                    "attributes":{"a":1,"b":2},
                    "revision":1,
                    "run_id":"r",
                    "name":"RUN_CREATED"
                })
            )
            .unwrap()
        );
    }

    #[test]
    fn float_rejected() {
        assert!(event_hash("GENESIS", 1, &serde_json::json!({"x":1.5})).is_err());
    }
}

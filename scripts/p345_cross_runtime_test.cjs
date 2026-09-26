const fs=require("fs"),cp=require("child_process");
const rt=require("../.tmp/p345-ts/contracts/p345_runtime.js");
const sdk=require("../.tmp/p345-ts/contracts/p345_extension_sdk.js");
const ir=JSON.parse(fs.readFileSync("benchmarks/p345_runtime_fixture.json","utf8"));
const replayBin=process.env.P345_REPLAY_BIN||"p345-replay";

const compiled=rt.compileAuthoringIR({ir});
if(compiled.actions.snapshot!=="EXECUTE"||compiled.actions.format!=="EXECUTE"||compiled.actions.render!=="WAIT_EXTERNAL")throw new Error("unexpected initial plan");
let state=rt.createRun(compiled);
state=rt.transitionRuntime({state,command:{type:"START_NODE",node_id:"snapshot"}});
state=rt.transitionRuntime({state,command:{type:"COMMIT_NODE",node_id:"snapshot",revision:1,output_sha256:"a".repeat(64),receipt_sha256:"1".repeat(64)}});
state=rt.transitionRuntime({state,command:{type:"START_NODE",node_id:"format"}});
state=rt.transitionRuntime({state,command:{type:"COMMIT_NODE",node_id:"format",revision:2,output_sha256:"b".repeat(64),receipt_sha256:"2".repeat(64)}});
state=rt.transitionRuntime({state,command:{type:"WAIT_NODE",node_id:"render"}});
state=rt.transitionRuntime({state,command:{type:"RESOLVE_NODE",node_id:"render",output_sha256:"c".repeat(64),receipt_sha256:"3".repeat(64)}});
state=rt.transitionRuntime({state,command:{type:"COMPLETE_RUN"}});
const replay=JSON.parse(cp.execFileSync(replayBin,["verify"],{input:JSON.stringify(state),encoding:"utf8"}));
if(!replay.ok||!replay.completed||replay.head_event_hash!==state.head_event_hash)throw new Error("Rust replay mismatch");

const prior={snapshot:{node_spec_sha256:compiled.node_spec_sha256.snapshot,provider_binding_sha256:compiled.provider_binding_sha256.snapshot,output_sha256:"a".repeat(64),terminal_state:"COMMITTED"}};
const sameBase=rt.compileAuthoringIR({ir,prior_snapshot:prior});
if(sameBase.actions.snapshot!=="REUSE")throw new Error("same-base PURE snapshot should reuse");
const nextBase=rt.compileAuthoringIR({ir:{...ir,base_revision:2},prior_snapshot:prior});
if(nextBase.actions.snapshot!=="EXECUTE")throw new Error("cross-revision PURE snapshot reuse must fail closed");
const changed=rt.compileAuthoringIR({ir,prior_snapshot:prior,changed_node_ids:["snapshot"]});
if(!changed.affected_nodes.includes("format")||!changed.affected_nodes.includes("render"))throw new Error("transitive invalidation failed");

const extension=sdk.defineExtension({
  extension_id:"fixture-ext",
  version:"1.0.0",
  node_kinds:[sdk.pureNode("document.snapshot.alias","document.inspect","DOCUMENT_SNAPSHOT",{capability_version:"1.0.0",evidence:["STRUCTURAL_NATIVE_FACT"]})]
});
const checked=rt.validateExtensionManifest(extension);
if(!checked.manifest_sha256)throw new Error("extension manifest was not sealed");
const extIr={schema:"chatgpt-web-hwpx-mcp/p3.45/authoring-ir/v1",ir_id:"extension-fixture",document_id:"doc_fixture",base_revision:1,nodes:[{id:"ext",kind:"document.snapshot.alias",inputs:{view:"document"},reusable:true}]};
const extPlan=rt.compileAuthoringIR({ir:extIr,extensions:[extension]});
if(extPlan.provider_bindings.ext.primary.provider_id!=="extension:fixture-ext")throw new Error("extension capability provider was not bound deterministically");

let aborted=rt.createRun(compiled);
aborted=rt.transitionRuntime({state:aborted,command:{type:"ABORT_RUN",reason_code:"test.cancelled"}});
const abortReplay=JSON.parse(cp.execFileSync(replayBin,["verify"],{input:JSON.stringify(aborted),encoding:"utf8"}));
if(!abortReplay.aborted||abortReplay.status!=="ABORTED")throw new Error("Rust abort replay mismatch");

const tampered=JSON.parse(JSON.stringify(state));
tampered.current_revision=999;
const bad=cp.spawnSync(replayBin,["verify"],{input:JSON.stringify(tampered),encoding:"utf8"});
if(bad.status===0)throw new Error("Rust verifier accepted tampered materialized revision");

const obs=rt.observability(state);
if(obs.event_count!==8||obs.committed_nodes!==3)throw new Error("observability mismatch");
console.log(JSON.stringify({status:"PASS",events:state.events.length,head:state.head_event_hash,affected:changed.affected_nodes,extension_provider:extPlan.provider_bindings.ext.primary.provider_id}));

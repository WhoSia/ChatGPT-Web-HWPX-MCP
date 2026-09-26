declare const process:any;
declare function require(name:string):any;
const fs=require("fs");
const kernel=require("../contracts/p346_capability_kernel");

function read(){
  const raw=fs.readFileSync(0,"utf8");
  return raw.trim()?JSON.parse(raw):{};
}
async function main(){
  const cmd=String(process.argv[2]||"");
  const input=read();
  let out:any;
  if(cmd==="contract")out=kernel.P346_PLATFORM_CONTRACT;
  else if(cmd==="project-tools")out=kernel.projectToolSurface(input.extensions||[]);
  else if(cmd==="validate-extension")out=kernel.validateExtensionManifest(input);
  else if(cmd==="validate-composition")out=kernel.validateEffectComposition(input);
  else if(cmd==="validate-sequence")out=kernel.validateToolSequence(input.effects||[]);
  else if(cmd==="inspect")out=kernel.inspectLegacyRuntime(input.state);
  else if(cmd==="diagnostics")out=kernel.runtimeDiagnostics(input.state);
  else if(cmd==="codegen")out=kernel.codegen(input.extensions||[]);
  else if(cmd==="run-wasm")out=await kernel.executeSandboxedWasm(input);
  else throw new Error("usage: p346-platform-cli contract|project-tools|validate-extension|validate-composition|validate-sequence|inspect|diagnostics|codegen|run-wasm");
  process.stdout.write(JSON.stringify(out)+"\n");
}
main().catch((err:any)=>{
  process.stderr.write(String(err&&err.stack||err)+"\n");
  process.exit(1);
});

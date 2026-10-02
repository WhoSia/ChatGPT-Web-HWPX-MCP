export {};
declare const process:any;
declare function require(name:string):any;
const fs=require("fs");
const rt=require("../contracts/p345_runtime");
function read(){const raw=fs.readFileSync(0,"utf8");return raw.trim()?JSON.parse(raw):{};}
const cmd=String(process.argv[2]||"");
let out:any;
if(cmd==="contract")out=rt.P345_RUNTIME_CONTRACT;
else if(cmd==="compile")out=rt.compileAuthoringIR(read());
else if(cmd==="create-run")out=rt.createRun(read());
else if(cmd==="transition")out=rt.transitionRuntime(read());
else if(cmd==="time-travel"){const x=read();out=rt.timeTravel(x.state,Number(x.seq));}
else if(cmd==="observability")out=rt.observability(read().state);
else if(cmd==="validate-extension")out=rt.validateExtensionManifest(read());
else throw new Error("usage: p345-runtime-cli contract|compile|create-run|transition|time-travel|observability|validate-extension");
process.stdout.write(JSON.stringify(out)+"\n");

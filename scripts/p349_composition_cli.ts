declare const process:any;
import {analyzeComposition,compositionContract} from "../contracts/p349_composition_kernel";
function readStdin():Promise<string>{
  return new Promise((resolve,reject)=>{let raw="";process.stdin.setEncoding("utf8");process.stdin.on("data",(c:string)=>raw+=c);process.stdin.on("end",()=>resolve(raw));process.stdin.on("error",reject);});
}
async function main(){
  const cmd=String(process.argv[2]||"contract");
  const raw=await readStdin();const input:any=raw.trim()?JSON.parse(raw):{};
  let out:any;
  if(cmd==="contract") out=compositionContract();
  else if(cmd==="analyze") out=analyzeComposition(input);
  else throw new Error("unknown command");
  process.stdout.write(JSON.stringify(out));
}
main().catch((e:any)=>{process.stderr.write(String(e&&e.message||e));process.exit(2);});
export {};

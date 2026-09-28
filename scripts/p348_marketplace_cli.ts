declare const process:any;
import {marketplaceContract,normalizeMarketplaceEvent,reduceMarketplaceEvents,discoverMarketplaceCandidates} from "../contracts/p348_marketplace_kernel";
function readStdin():Promise<string>{
  return new Promise((resolve,reject)=>{let raw="";process.stdin.setEncoding("utf8");process.stdin.on("data",(c:string)=>raw+=c);process.stdin.on("end",()=>resolve(raw));process.stdin.on("error",reject);});
}
async function main(){
  const command=String(process.argv[2]||"contract");
  const raw=await readStdin();const payload=raw.trim()?JSON.parse(raw):{};
  let result:any;
  if(command==="contract") result=marketplaceContract();
  else if(command==="event") result=normalizeMarketplaceEvent(payload.event??payload);
  else if(command==="reduce") result=reduceMarketplaceEvents(payload.events||[]);
  else if(command==="discover") result=discoverMarketplaceCandidates(payload.state,payload.request||{});
  else throw new Error("unknown P3.48 command");
  process.stdout.write(JSON.stringify(result));
}
main().catch((e:any)=>{process.stderr.write(String(e&&e.message||e));process.exit(1);});
export {};

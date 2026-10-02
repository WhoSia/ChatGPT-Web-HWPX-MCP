declare const process:any;
import {
  supplyChainContract,
  normalizePackage,
  verifyDependencyClosure,
  compareReproducibleBuilds,
  solveCompatibility,
  compareHostConformance,
  certifyPackage,
  verifyCertificateSeal,
  validateRolloutTransition,
  validateCertifiedRollback,
} from "../contracts/p347_supply_chain_kernel";

function readStdin():Promise<string>{
  return new Promise((resolve,reject)=>{
    let raw="";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data",(c:string)=>raw+=c);
    process.stdin.on("end",()=>resolve(raw));
    process.stdin.on("error",reject);
  });
}
async function main(){
  const command=String(process.argv[2]||"contract");
  const raw=await readStdin();
  const payload=raw.trim()?JSON.parse(raw):{};
  let result:any;
  if(command==="contract") result=supplyChainContract();
  else if(command==="package") result=normalizePackage(payload.package??payload);
  else if(command==="dependencies") result=verifyDependencyClosure(payload.package,payload.catalog||[]);
  else if(command==="reproducibility") result=compareReproducibleBuilds(payload.left,payload.right);
  else if(command==="compatibility") result=solveCompatibility(payload.current,payload.candidate);
  else if(command==="conformance") result=compareHostConformance(payload.observations||[]);
  else if(command==="certify") result=certifyPackage(payload.package,payload.catalog||[],payload.evidence||[],payload.host_observations||[]);
  else if(command==="verify-certificate") result=verifyCertificateSeal(payload.certificate??payload);
  else if(command==="transition") result=validateRolloutTransition(payload.from,payload.to,payload.certificate||{});
  else if(command==="rollback") result=validateCertifiedRollback(payload.current_certificate||{},payload.target_certificate||{});
  else throw new Error("unknown P3.47 command");
  process.stdout.write(JSON.stringify(result));
}
main().catch((e:any)=>{process.stderr.write(String(e&&e.message||e));process.exit(1);});
export {};

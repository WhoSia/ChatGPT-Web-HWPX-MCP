use std::io::{self,Read};
fn main(){
    let args:Vec<String>=std::env::args().collect();
    if args.len()==2&&args[1]=="--contract"{println!("p3.48-marketplace-verifier-v1");return;}
    if args.len()!=2{eprintln!("usage: p348-marketplace-verifier --contract | verify-checkpoint | verify-bundle");std::process::exit(2);}
    let mut raw=String::new();io::stdin().read_to_string(&mut raw).unwrap();
    let value:serde_json::Value=match serde_json::from_str(&raw){Ok(v)=>v,Err(e)=>{eprintln!("{e}");std::process::exit(1)}};
    let result=match args[1].as_str(){
        "verify-bundle"=>p348_marketplace_verifier::verify_bundle(&value),
        "verify-checkpoint"=>{
            let o=match value.as_object(){Some(x)=>x,None=>{eprintln!("expected object");std::process::exit(1)}};
            match (o.get("checkpoint"),o.get("trust_policy")){
                (Some(cp),Some(policy))=>p348_marketplace_verifier::verify_checkpoint(cp,policy),
                _=>Err("verify-checkpoint requires checkpoint and trust_policy".into()),
            }
        },
        _=>Err("unknown P3.48 verifier command".into()),
    };
    match result{Ok(v)=>println!("{}",serde_json::to_string(&v).unwrap()),Err(e)=>{eprintln!("{e}");std::process::exit(1)}}
}

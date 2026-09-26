use std::io::{self,Read};
fn main(){
    let args:Vec<String>=std::env::args().collect();
    if args.len()==2&&args[1]=="--contract"{println!("p3.47-certification-guard-v1");return;}
    if args.len()!=2{eprintln!("usage: p347-certifier --contract | check-certificate | check-transition | check-compatibility | check-rollback");std::process::exit(2);}
    let mut raw=String::new();io::stdin().read_to_string(&mut raw).unwrap();
    let value:serde_json::Value=match serde_json::from_str(&raw){Ok(v)=>v,Err(e)=>{eprintln!("{e}");std::process::exit(1)}};
    let result=match args[1].as_str(){
        "check-certificate"=>p347_certifier::verify_certificate(&value),
        "check-transition"=>p347_certifier::verify_transition(&value),
        "check-compatibility"=>p347_certifier::verify_compatibility(&value),
        "check-rollback"=>p347_certifier::verify_rollback(&value),
        _=>Err("unknown command".into()),
    };
    match result{Ok(v)=>println!("{}",serde_json::to_string(&v).unwrap()),Err(e)=>{eprintln!("{e}");std::process::exit(1)}}
}

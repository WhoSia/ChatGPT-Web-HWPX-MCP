use std::io::{self,Read};

fn main(){
    let args:Vec<String>=std::env::args().collect();
    if args.len()==2&&args[1]=="--contract"{
        println!("p3.46-effect-guard-v1");
        return;
    }
    if args.len()!=2{
        eprintln!("usage: p346-guard --contract | check-plan | check-sequence");
        std::process::exit(2);
    }
    let mut raw=String::new();
    io::stdin().read_to_string(&mut raw).unwrap();
    let value:serde_json::Value=match serde_json::from_str(&raw){
        Ok(v)=>v,
        Err(e)=>{eprintln!("{e}");std::process::exit(1)}
    };
    let result=match args[1].as_str(){
        "check-plan"=>p346_guard::verify_effect_plan(&value),
        "check-sequence"=>p346_guard::verify_tool_sequence(&value),
        _=>Err("unknown command".into()),
    };
    match result{
        Ok(v)=>println!("{}",serde_json::to_string(&v).unwrap()),
        Err(e)=>{eprintln!("{e}");std::process::exit(1);}
    }
}

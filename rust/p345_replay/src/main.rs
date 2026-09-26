use std::io::{self,Read};
fn main(){
 let args:Vec<String>=std::env::args().collect();
 if args.len()==2&&args[1]=="--contract"{println!("p3.45-replay-v1");return;}
 if args.len()!=2||args[1]!="verify"{eprintln!("usage: p345-replay --contract | verify");std::process::exit(2);}
 let mut raw=String::new();io::stdin().read_to_string(&mut raw).unwrap();
 let value:serde_json::Value=serde_json::from_str(&raw).unwrap();
 match p345_replay::verify_state(&value){Ok(v)=>println!("{}",serde_json::to_string(&v).unwrap()),Err(e)=>{eprintln!("{}",e);std::process::exit(1);}}
}

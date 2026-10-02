use std::env;
use p344_gate::decide;

fn parse_bool(s: &str) -> bool {
    match s {
        "true" | "1" | "TRUE" => true,
        "false" | "0" | "FALSE" => false,
        _ => panic!("invalid bool: {}", s),
    }
}

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() == 2 && args[1] == "--contract" {
        println!("p3.44-gate-v1");
        return;
    }
    if args.len() != 11 {
        eprintln!("usage: p344-gate STATIC RENDER_REQUIREMENT RENDER_VERDICT REPAIRABLE REPAIRS_USED MAX_REPAIRS POLICY_OK FOOTPRINT_OK HUMAN_REQUIREMENT HUMAN_VERDICT");
        std::process::exit(2);
    }
    let d = decide(
        &args[1], &args[2], &args[3], parse_bool(&args[4]),
        args[5].parse().expect("repairs_used"), args[6].parse().expect("max_repairs"),
        parse_bool(&args[7]), parse_bool(&args[8]), &args[9], &args[10],
    );
    println!("{}|{}", d.action.as_str(), d.reason);
}

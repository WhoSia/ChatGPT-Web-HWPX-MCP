#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Action { Repair, WaitRender, WaitHuman, Deliver, Hold }

impl Action {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Repair => "REPAIR",
            Self::WaitRender => "WAIT_RENDER",
            Self::WaitHuman => "WAIT_HUMAN",
            Self::Deliver => "DELIVER",
            Self::Hold => "HOLD",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Decision { pub action: Action, pub reason: &'static str }

pub fn decide(
    static_verdict: &str,
    render_requirement: &str,
    render_verdict: &str,
    repairable: bool,
    repairs_used: u8,
    max_repairs: u8,
    policy_ok: bool,
    footprint_ok: bool,
    human_requirement: &str,
    human_verdict: &str,
) -> Decision {
    if !policy_ok { return Decision { action: Action::Hold, reason: "POLICY_GATE_FAILED" }; }
    if !footprint_ok { return Decision { action: Action::Hold, reason: "PRESERVATION_GATE_FAILED" }; }

    if static_verdict == "NEEDS_REPAIR" {
        if repairs_used >= max_repairs {
            return Decision { action: Action::Hold, reason: "REPAIR_LIMIT_EXHAUSTED" };
        }
        if !repairable {
            return Decision { action: Action::Hold, reason: "STATIC_REPAIR_GAP" };
        }
        return Decision { action: Action::Repair, reason: "STATIC_REPAIR_REQUIRED" };
    }

    let render_provided = render_verdict != "NOT_PROVIDED" && render_verdict != "PENDING";
    if render_requirement == "REQUIRED" {
        if !render_provided {
            return Decision { action: Action::WaitRender, reason: "RENDER_EVIDENCE_REQUIRED" };
        }
        if render_verdict == "INVALID" {
            return Decision { action: Action::Hold, reason: "RENDER_EVIDENCE_INVALID" };
        }
        if render_verdict == "NEEDS_REPAIR" {
            if repairs_used >= max_repairs {
                return Decision { action: Action::Hold, reason: "REPAIR_LIMIT_EXHAUSTED" };
            }
            if !repairable {
                return Decision { action: Action::Hold, reason: "RENDER_REPAIR_GAP" };
            }
            return Decision { action: Action::Repair, reason: "RENDER_REPAIR_REQUIRED" };
        }
    } else if render_requirement == "WHEN_AVAILABLE" && render_provided {
        if render_verdict == "INVALID" {
            return Decision { action: Action::Hold, reason: "RENDER_EVIDENCE_INVALID" };
        }
        if render_verdict == "NEEDS_REPAIR" {
            if repairs_used >= max_repairs {
                return Decision { action: Action::Hold, reason: "REPAIR_LIMIT_EXHAUSTED" };
            }
            if !repairable {
                return Decision { action: Action::Hold, reason: "RENDER_REPAIR_GAP" };
            }
            return Decision { action: Action::Repair, reason: "RENDER_REPAIR_REQUIRED" };
        }
    }

    if human_requirement == "REQUIRED" {
        if human_verdict == "PENDING" {
            return Decision { action: Action::WaitHuman, reason: "HUMAN_REVIEW_REQUIRED" };
        }
        if human_verdict == "FAIL" {
            return Decision { action: Action::Hold, reason: "HUMAN_REVIEW_FAILED" };
        }
    }

    Decision { action: Action::Deliver, reason: "ALL_REQUIRED_GATES_PASS" }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn b(s: &str) -> bool { s == "true" }

    #[test]
    fn golden_gate_parity() {
        let data = include_str!("../../../benchmarks/p344_gate_golden.tsv");
        let mut checked = 0usize;
        for line in data.lines().skip(1).filter(|x| !x.trim().is_empty()) {
            let c: Vec<&str> = line.split('\t').collect();
            assert_eq!(c.len(), 13, "fixture columns");
            let d = decide(
                c[1], c[2], c[3], b(c[4]), c[5].parse().unwrap(), c[6].parse().unwrap(),
                b(c[7]), b(c[8]), c[9], c[10]
            );
            assert_eq!(d.action.as_str(), c[11], "action fixture {}", c[0]);
            assert_eq!(d.reason, c[12], "reason fixture {}", c[0]);
            checked += 1;
        }
        assert!(checked > 0);
    }
}

#[derive(Debug, Clone, Copy)]
pub struct FootprintDecision {
    pub package_identical: bool,
    pub expected_declared: bool,
    pub unexpected_changed: u64,
    pub unexpected_added: u64,
    pub unexpected_removed: u64,
    pub missing_required: u64,
    pub record_drift: u64,
    pub require_record_identity: bool,
}

pub fn classify(input: FootprintDecision) -> &'static str {
    if input.package_identical {
        return "PACKAGE_IDENTICAL";
    }
    let record_divergence = input.require_record_identity && input.record_drift > 0;
    let diverged = input.unexpected_changed > 0
        || input.unexpected_added > 0
        || input.unexpected_removed > 0
        || input.missing_required > 0
        || record_divergence;
    if input.expected_declared && !diverged {
        "TARGETED_PARTS_ONLY"
    } else {
        "PACKAGE_VALID_ONLY"
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn golden_fixture_matches_exact_kernel() {
        let data = include_str!("../../../benchmarks/p342_footprint_grade_golden.tsv");
        for (idx, line) in data.lines().enumerate() {
            if idx == 0 || line.trim().is_empty() {
                continue;
            }
            let c: Vec<&str> = line.split('\t').collect();
            assert!(c.len() >= 10, "bad fixture row: {line}");
            let input = FootprintDecision {
                package_identical: c[1] == "1",
                expected_declared: c[2] == "1",
                unexpected_changed: c[3].parse().unwrap(),
                unexpected_added: c[4].parse().unwrap(),
                unexpected_removed: c[5].parse().unwrap(),
                missing_required: c[6].parse().unwrap(),
                record_drift: c[7].parse().unwrap(),
                require_record_identity: c[8] == "1",
            };
            assert_eq!(classify(input), c[9], "case {}", c[0]);
        }
    }
}

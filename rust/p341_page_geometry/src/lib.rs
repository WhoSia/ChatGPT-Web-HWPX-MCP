pub const PPM: u64 = 1_000_000;

#[derive(Debug, Clone)]
pub struct PagePrimitive {
    pub width: u64,
    pub height: u64,
    pub line_count: u64,
    pub left: u64,
    pub right: u64,
    pub top: u64,
    pub bottom: u64,
    pub line_area: u64,
    pub largest_gap: u64,
    pub top_area: u64,
    pub bottom_area: u64,
}

#[derive(Debug, Clone, Copy)]
struct Thresholds {
    max_lines: u64,
    max_vertical_span_ppm: u64,
    max_line_area_ppm: u64,
    max_internal_gap_ppm: u64,
    max_balance_delta_ppm: u64,
}

fn thresholds(archetype: &str) -> Thresholds {
    match archetype {
        "RESEARCH_BRIEF" => Thresholds { max_lines: 48, max_vertical_span_ppm: 885_000, max_line_area_ppm: 180_000, max_internal_gap_ppm: 190_000, max_balance_delta_ppm: 500_000 },
        "INSTITUTIONAL_REPORT" => Thresholds { max_lines: 54, max_vertical_span_ppm: 905_000, max_line_area_ppm: 200_000, max_internal_gap_ppm: 220_000, max_balance_delta_ppm: 540_000 },
        "ACADEMIC_REPORT" => Thresholds { max_lines: 58, max_vertical_span_ppm: 920_000, max_line_area_ppm: 220_000, max_internal_gap_ppm: 230_000, max_balance_delta_ppm: 560_000 },
        "FORM" => Thresholds { max_lines: 60, max_vertical_span_ppm: 930_000, max_line_area_ppm: 240_000, max_internal_gap_ppm: 260_000, max_balance_delta_ppm: 620_000 },
        _ => Thresholds { max_lines: 52, max_vertical_span_ppm: 900_000, max_line_area_ppm: 190_000, max_internal_gap_ppm: 210_000, max_balance_delta_ppm: 520_000 },
    }
}

fn ppm(n: u64, d: u64) -> u64 {
    if d == 0 { 0 } else { (n.saturating_mul(PPM) + d / 2) / d }
}

pub fn analyze_page(p: &PagePrimitive, archetype: &str) -> Vec<&'static str> {
    let t = thresholds(archetype);
    let vertical_span = p.bottom.saturating_sub(p.top);
    let vertical_span_ppm = ppm(vertical_span, p.height);
    let line_area_ppm = ppm(p.line_area, p.width.saturating_mul(p.height));
    let gap_ppm = ppm(p.largest_gap, p.height);
    let half_total = p.top_area.saturating_add(p.bottom_area);
    let balance_ppm = ppm(p.top_area.abs_diff(p.bottom_area), half_total);
    let mut codes = Vec::new();

    if p.line_count >= t.max_lines || vertical_span_ppm >= t.max_vertical_span_ppm || line_area_ppm >= t.max_line_area_ppm {
        codes.push("PAGE_COMPOSITION_OVERFULL");
    }
    if p.line_count >= 8 && gap_ppm >= t.max_internal_gap_ppm {
        codes.push("PAGE_RHYTHM_LARGE_WHITESPACE_BAND");
    }
    if p.line_count >= 8 && vertical_span_ppm >= 500_000 && balance_ppm >= t.max_balance_delta_ppm {
        if p.top_area > p.bottom_area {
            codes.push("PAGE_TOP_HEAVY_COMPOSITION");
        } else {
            codes.push("PAGE_BOTTOM_HEAVY_COMPOSITION");
        }
    }
    codes
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn golden_fixture_matches_exact_kernel() {
        let data = include_str!("../../../benchmarks/p341_page_geometry_golden.tsv");
        for (idx, line) in data.lines().enumerate() {
            if idx == 0 || line.trim().is_empty() { continue; }
            let c: Vec<&str> = line.split('\t').collect();
            assert!(c.len() >= 14, "bad fixture row: {line}");
            let p = PagePrimitive {
                width: c[2].parse().unwrap(),
                height: c[3].parse().unwrap(),
                line_count: c[4].parse().unwrap(),
                left: c[5].parse().unwrap(),
                right: c[6].parse().unwrap(),
                top: c[7].parse().unwrap(),
                bottom: c[8].parse().unwrap(),
                line_area: c[9].parse().unwrap(),
                largest_gap: c[10].parse().unwrap(),
                top_area: c[11].parse().unwrap(),
                bottom_area: c[12].parse().unwrap(),
            };
            let actual = analyze_page(&p, c[1]).join(",");
            assert_eq!(actual, c[13], "case {}", c[0]);
        }
    }
}

export type CompositionArchetype =
  | "POLISHED_REPORT"
  | "RESEARCH_BRIEF"
  | "INSTITUTIONAL_REPORT"
  | "ACADEMIC_REPORT"
  | "FORM";

export type CompositionFindingCode =
  | "PAGE_COMPOSITION_OVERFULL"
  | "PAGE_RHYTHM_LARGE_WHITESPACE_BAND"
  | "PAGE_TOP_HEAVY_COMPOSITION"
  | "PAGE_BOTTOM_HEAVY_COMPOSITION"
  | "PAGE_BOUNDARY_SINGLE_LINE_PARAGRAPH"
  | "PAGE_BOUNDARY_SINGLE_LINE_BLOCK_RISK"
  | "DOCUMENT_PAGE_DENSITY_VARIANCE_HIGH";

export interface PageCompositionThresholds {
  max_lines: number;
  max_vertical_span_ppm: number;
  max_line_area_ppm: number;
  max_internal_gap_ppm: number;
  max_balance_delta_ppm: number;
}

export const PAGE_COMPOSITION_THRESHOLDS: Readonly<Record<CompositionArchetype, PageCompositionThresholds>> = {
  POLISHED_REPORT: { max_lines: 52, max_vertical_span_ppm: 900000, max_line_area_ppm: 190000, max_internal_gap_ppm: 210000, max_balance_delta_ppm: 520000 },
  RESEARCH_BRIEF: { max_lines: 48, max_vertical_span_ppm: 885000, max_line_area_ppm: 180000, max_internal_gap_ppm: 190000, max_balance_delta_ppm: 500000 },
  INSTITUTIONAL_REPORT: { max_lines: 54, max_vertical_span_ppm: 905000, max_line_area_ppm: 200000, max_internal_gap_ppm: 220000, max_balance_delta_ppm: 540000 },
  ACADEMIC_REPORT: { max_lines: 58, max_vertical_span_ppm: 920000, max_line_area_ppm: 220000, max_internal_gap_ppm: 230000, max_balance_delta_ppm: 560000 },
  FORM: { max_lines: 60, max_vertical_span_ppm: 930000, max_line_area_ppm: 240000, max_internal_gap_ppm: 260000, max_balance_delta_ppm: 620000 },
} as const;

export interface PageCompositionDiagnostic {
  schema: "chatgpt-web-hwpx-mcp/p3.41/page-composition/v1";
  phase: "P3.41";
  archetype: CompositionArchetype;
  authority: "HANCOM_NATIVE_RENDER_EVIDENCE" | "EXTERNAL_RENDER_OBSERVATION";
  world_contact_valid: boolean;
  capture_sha256: string;
  page_count: number;
  finding_count: number;
  verdict: "PASS" | "PASS_WITH_WARNINGS" | "REVIEW_REQUIRED";
}

export type PreservationGrade =
  | "PACKAGE_VALID_ONLY"
  | "TARGETED_PARTS_ONLY"
  | "PACKAGE_IDENTICAL";

export interface FootprintDecisionInput {
  package_identical: boolean;
  expected_declared: boolean;
  unexpected_changed: number;
  unexpected_added: number;
  unexpected_removed: number;
  missing_required: number;
  untouched_record_metadata_changed?: number;
  require_untouched_record_metadata?: boolean;
}

export interface MutationFootprintCertificate {
  schema: "chatgpt-web-hwpx-mcp/p3.42/mutation-footprint-certificate/v1";
  phase: "P3.42";
  preservation: {
    actual_grade: PreservationGrade;
    whole_package_identical: boolean;
    untouched_part_payloads: { verified: number; changed: number };
    untouched_record_metadata: {
      verified: number;
      changed: number;
      required_for_grade: boolean;
    };
  };
  divergence: {
    unexpected_changed_parts: string[];
    unexpected_added_parts: string[];
    unexpected_removed_parts: string[];
    missing_required_changed_parts: string[];
    count: number;
  };
  authority: "MEASURED_PACKAGE_PART_FOOTPRINT_NOT_VISUAL_OR_SEMANTIC_CORRECTNESS";
}

export function classifyFootprintGrade(
  input: FootprintDecisionInput,
): PreservationGrade {
  if (input.package_identical) return "PACKAGE_IDENTICAL";
  const recordDivergence =
    Boolean(input.require_untouched_record_metadata) &&
    (input.untouched_record_metadata_changed ?? 0) > 0;
  const diverged =
    input.unexpected_changed > 0 ||
    input.unexpected_added > 0 ||
    input.unexpected_removed > 0 ||
    input.missing_required > 0 ||
    recordDivergence;
  if (input.expected_declared && !diverged) return "TARGETED_PARTS_ONLY";
  return "PACKAGE_VALID_ONLY";
}

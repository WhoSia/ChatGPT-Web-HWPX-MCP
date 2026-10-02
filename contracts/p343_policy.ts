export type PreservationGrade="PACKAGE_IDENTICAL"|"TARGETED_PARTS_ONLY"|"PACKAGE_VALID_ONLY";
const rank:Record<PreservationGrade,number>={PACKAGE_VALID_ONLY:0,TARGETED_PARTS_ONLY:1,PACKAGE_IDENTICAL:2};
export function adjudicatePolicyGate(hardViolations:number,semanticPreserved:boolean,structurePreserved:boolean,grade:PreservationGrade):"PASS"|"FAIL"{
 return hardViolations===0&&semanticPreserved&&structurePreserved&&rank[grade]>=rank.TARGETED_PARTS_ONLY?"PASS":"FAIL";
}

# P3.34-R2 Implementation-Generated Resolution Round-Trip

Native evidence has established whole-document Accept All / Reject All semantics
for P3.22-authored Insert/Delete/Replace and the protection boundary.

The implementation candidate is intentionally narrower:

- unprotected documents only;
- whole-document Accept All or Reject All only;
- header change types must be Insert/Delete;
- tracked markers must be simple direct children of hp:t;
- no mixed inline markup inside a tracked span;
- protected documents fail closed without password verification;
- selective per-change resolution remains unsupported.

This pack creates four implementation-generated resolved outputs covering both
decisions and both Insert/Delete effects, including paired Replace:

- candidate-insert-accept
- candidate-delete-reject
- candidate-replace-accept
- candidate-replace-reject

The user performs no review operation. Each file is only opened in Hancom and
saved unchanged. The analyzer requires final text, zero tracked changes/authors,
package validity, and post-Hancom semantic preservation.

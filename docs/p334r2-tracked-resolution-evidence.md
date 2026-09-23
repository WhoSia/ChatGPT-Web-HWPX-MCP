# P3.34-R2 — Tracked-Change Native Resolution Evidence Protocol

## Goal

Measure Hancom-native semantics for accepting/rejecting P3.22-authored tracked
insert/delete/replace changes before implementing any resolution mutation.

Production authority remains:

`READ_PRESERVE_ONLY_FOR_RESOLUTION`

until native before/after evidence closes the operation semantics.

## First capture matrix

| Case | P3.22 authored change | Hancom action | Expected visible result |
|---|---|---|---|
| insert-accept | insert ` +inserted` | accept all | `alpha base +inserted` |
| insert-reject | insert ` +inserted` | reject all | `alpha base` |
| delete-accept | delete `remove ` | accept all | `beta target` |
| delete-reject | delete `remove ` | reject all | `beta remove target` |
| replace-accept | old→new | accept all | `gamma new value` |
| replace-reject | old→new | reject all | `gamma old value` |
| protection-enable | tracked insert | enable change-protection with fixed probe password | encryption subtree must appear |

The analyzer requires resolution cases to remove body insert/delete boundary marks
and header track-change entries while producing the expected final text.

The protection probe does not promote password authoring. It only determines
whether Hancom materializes a durable track-change encryption subtree and gives
the next probe a real native protected artifact.

## Protection boundary

Pinned P3.22 can read/preserve tracked changes but does not author the
track-change protection encryption structure. Upstream reverse mapping indicates
Hancom stores protection under the track-change configuration as an encryption
child, but P3.34-R2 does not synthesize that structure from description alone.

If the first protection capture succeeds, R2 continues with a second bounded
probe against the native protected artifact to distinguish:

- no-password refusal / protected state;
- correct-password resolution;
- post-resolution protection/config retention or retirement.

## Product guard

This lane must not change the P3.33 create/edit/validate/deliver primary path.
Any later promotion must reuse P3.22 revision custody and atomic transaction
machinery, then rerun OAuth/Docker/P3.33 delivery regression.

# P3.34-R2 Native Tracked-Change Resolution Receipt — Stage 1

## Capture provenance

- Hancom: 13.0.0.3622
- Capture cases: 7/7 completed
- ZIP CRC/XML parse: PASS for all cases
- Resolution analyzer result: 6/6 semantic cases PASS
- Initial protection analyzer result: false negative caused by an incorrect expected tag shape, not by user execution

## Resolution semantics

### Insert
- accept: tracked inserted text becomes ordinary visible text
- reject: tracked inserted text disappears
- both cases retire body insertBegin/insertEnd markers
- both cases retire header trackChanges/trackChangeAuthors entries

### Delete
- accept: tracked deleted text is physically removed from final visible text
- reject: tracked deleted text is restored/preserved
- both cases retire body deleteBegin/deleteEnd markers
- both cases retire header track-change entries

### Replace
P3.22 represents replace as paired Delete + Insert changes.

- accept-all: final text keeps the inserted/new side and removes the deleted/old side
- reject-all: final text keeps the deleted/old side and removes the inserted/new side
- both member changes and all body markers are retired

This establishes whole-document accept-all/reject-all semantics for P3.22-authored
insert/delete/replace specimens. Per-change selective resolution is not yet
promoted by this evidence.

## Native protection encoding

The native protection probe succeeded.

Hancom 13.0.0.3622 stores change-protection under:

`hh:trackchageConfig/config:config-item-set[@name="TrackChangePasswordInfo"]`

Observed child config items:

- `algorithm-name` = `SHA1`
- `salt` = base64Binary
- `spin-count` = `50000`
- `hash` = base64Binary

The tracked change itself remained unresolved and the protection metadata was
added durably. The first analyzer expected a differently named encryption
element and therefore produced a false-negative protection verdict.

No password writer is promoted from this observation alone. R2 must now use
the native protected artifact for a second boundary probe.

## Stage-1 verdict

**ACCEPT_ALL_REJECT_ALL_NATIVE_SEMANTICS_PASS /
TRACK_CHANGE_PASSWORD_INFO_NATIVE_ENCODING_PASS /
PROTECTION_RESOLUTION_BOUNDARY_PENDING**

Production authority remains read/preserve-only for resolution until the
protected-artifact boundary and implementation-generated Hancom round-trip
are closed.

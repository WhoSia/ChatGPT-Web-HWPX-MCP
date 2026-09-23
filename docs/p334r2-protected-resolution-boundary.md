# P3.34-R2 Protected-Resolution Boundary Probe

Stage one established that Hancom 13.0.0.3622 stores tracked-change protection
as `hh:trackchageConfig/config:config-item-set[@name="TrackChangePasswordInfo"]`
with SHA1, salt, spin-count 50000, and hash.

This second probe reuses that **native protected artifact**. It does not synthesize
or alter password metadata.

Cases:

1. `protected-cancel-accept`: attempt Accept All, cancel the password prompt,
   save. The unresolved tracked change and password info must remain.
2. `protected-correct-accept`: Accept All with password `P334R2!`, save.
   Final text must contain the inserted text and tracked changes must retire.
3. `protected-correct-reject`: Reject All with the same password, save.
   Final text must exclude the inserted text and tracked changes must retire.

The analyzer also records whether `TrackChangePasswordInfo` remains after
successful resolution; this determines protection/config retirement semantics.

Production accept/reject authority remains closed until this probe and a later
implementation-generated Hancom round-trip pass.

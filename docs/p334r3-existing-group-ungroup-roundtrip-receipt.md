# P3.34-R3 Implementation-Generated Hancom Round-Trip Receipt

## Result

User-returned `p334r3-candidate-roundtrip-pack-captured.zip` passed all 3 implementation-generated Hancom open/save cases.

- `candidate-group-existing`
  - before SHA-256: `81569071bef2b7863456934ad12e078066fe956209aed49187b45991e72198ae`
  - after SHA-256: `189a8bb9128fb2f15dedf9b374d255060e88b233f0ba73322f7c276f3a15d21b`
  - semantic state preserved: one container, two ellipse members, group position `(9000,7000)`, size `19200×9000`, member offsets `(0,0)` and `(13000,4000)`
- `candidate-ungroup-existing`
  - before SHA-256: `5043379c1f13ef5d81563b3310bc88ebfa5642294d0707aa4ecd021817a9dafc`
  - after SHA-256: `d32c82e71d0aeca22abe0036c6aa3d35943cefa1ba46c66d27cf2052e7f0adc6`
  - semantic state preserved: two top-level rects at `(5000,6000)` and `(14000,8500)`
- `candidate-ungroup-translated`
  - before SHA-256: `80b29fb9eed55035be371b1684dd40af97f279616ed6faaba8f61f7d663c3cc5`
  - after SHA-256: `f13d55280aaf495be9b5e931e1f67db0635971fd0146c4281b1588664ed89084`
  - semantic state preserved: two top-level rects at `(18000,12000)` and `(27000,14500)`

All three files changed bytes during Hancom save, but the bounded geometry/topology contract was preserved.

## Production authority

Promoted:

`EXISTING_RECT_ELLIPSE_GROUP_UNGROUP_BOUNDED`

Operations:

- `group_existing_objects`
- `ungroup_existing_objects`

Bounds:

- grouping exactly two objects;
- rect/ellipse only;
- floating only;
- one shared paragraph anchor and coordinate frame;
- no rotation, scaling, flipping, nested groups, inline objects, or other drawing families.

## Verdict

**IMPLEMENTATION_GENERATED_HANCOM_ROUNDTRIP_PASS /
EXISTING_RECT_ELLIPSE_GROUP_UNGROUP_BOUNDED_PROMOTED**

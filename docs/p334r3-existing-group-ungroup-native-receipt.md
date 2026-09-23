# P3.34-R3 Native Existing Group/Ungroup Evidence Receipt — Stage 1

## Capture

User-returned `p334r3-group-ungroup-pack-captured.zip` contains three diagnostic native Hancom specimens:

1. two independent floating ellipses → Group;
2. generated group → Ungroup;
3. translated generated group → Ungroup.

All three structural analyzers PASS.

## Native grouping semantics

For the ellipse pair:

- object A: page/paragraph-relative position `(9000,7000)`, size `7200×4200`;
- object B: position `(22000,11000)`, size `6200×5000`.

Hancom groups them as:

- container position = componentwise minimum = `(9000,7000)`;
- container size = union bounding box = `19200×9000`;
- child A local offset = `(0,0)`;
- child B local offset = `(13000,4000)`;
- child `instid` values are preserved;
- child top-level `id` values are retired to `0`;
- child `groupLevel` becomes `1`;
- child floating `hp:pos` / top-level size wrapper semantics move to the container;
- container inherits the shared anchor and position coordinate frame.

Thus for admitted unrotated objects:

`group_origin = (min(x_i), min(y_i))`

`child_local_i = (x_i - group_origin_x, y_i - group_origin_y)`

`group_size = (max(x_i+w_i)-min(x_i), max(y_i+h_i)-min(y_i))`.

## Native ungroup semantics

Two independent group positions were observed:

- group at `(5000,6000)`, child local offset `(9000,2500)` → ungrouped child at `(14000,8500)`;
- group at `(18000,12000)`, child local offset `(9500,3500)` → ungrouped child at `(27500,15500)`.

Therefore for the admitted unrotated/unscaled case:

`child_page_i = group_origin + child_local_i`.

Hancom additionally:

- preserves child `instid`;
- assigns new top-level object `id` values;
- sets `groupLevel=0`;
- resets child local offset/render translation to origin;
- materializes top-level `hp:sz`, `hp:pos`, margins/comment wrappers;
- uses the group anchor/coordinate frame for the released children;
- materializes ordinary floating wrap metadata (`SQUARE / BOTH_SIDES`) for the observed rectangle children.

## Explicit non-evidence

No authority is inferred for:

- rotated groups or rotated children;
- scaled groups;
- flipped groups;
- mixed anchors / different coordinate frames;
- nested groups;
- inline/treat-as-char objects;
- textboxes/images/lines/connectors;
- children with complex non-identity rendering transforms.

## Stage-1 verdict

**UNROTATED_SHARED_ANCHOR_REBASING_SEMANTICS_PASS /
BOUNDED_EXISTING_GROUP_UNGROUP_CANDIDATE_ELIGIBLE**

Implementation-generated Hancom open/save remains required before production promotion.

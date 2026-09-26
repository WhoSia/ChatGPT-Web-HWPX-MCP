# Autonomous Professional Authoring

P3.44 turns the design stack into a bounded resumable workflow.

## Default path

1. Call **get_autonomous_authoring_contract**.
2. Use **start_autonomous_professional_authoring** with a rich plan.
3. The runtime may apply only locator-bound repairs that pass the P3.42 mutation-footprint gate.
4. When the run returns `WAIT_RENDER`, obtain new render evidence. Do not deliver while required render evidence is absent.
5. Resume with **resume_autonomous_professional_authoring** using that evidence and the exact persisted run hash.
6. Any repair after render invalidates the old render and requires re-render.
7. Use **get_autonomous_authoring_run** to recover the persisted workflow state.

## Authority

Rust is the production repair/delivery gate. TypeScript independently reproduces gate semantics and scores AuthorBench blind packets. Python remains the HWPX-native adapter. PowerShell/Hancom supplies native world contact.

A static PASS is not a native-render PASS, and delivery is not a human visual approval.

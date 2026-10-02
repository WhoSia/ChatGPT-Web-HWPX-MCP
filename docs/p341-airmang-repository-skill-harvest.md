# P3.41 Airmang Repository & Skill Architecture Harvest

## Scope

This audit reviewed every public repository currently discoverable under `airmang` and then read the HWPX, skill, evidence, workflow, DIVE, and builder surfaces in depth. The purpose is selective transfer: preserve product boundaries and proven ideas without importing a second source of truth or copying whole implementations.

## Global adoption rule

> Borrow invariants and workflow architecture; reimplement against this repository's contracts.

- Do not fork or vendor airmang application logic into this MCP.
- Prefer upstream `python-hwpx` public APIs when they already own HWPX semantics.
- Skill files choose intent, workflow, and evidence requirements. MCP/runtime code owns deterministic execution.
- External evidence states are never inferred from static success.
- Any copied idea must have one canonical owner in this repository.

## Full public-repository inventory

| Repository | What was inspected | Relevance | Decision |
|---|---|---:|---|
| `python-hwpx` | README, safe-write contract, product boundary, package/probe/test layout | Very high | **ADOPT/UPSTREAM** — preservation grades, open-safety, measured mutation receipts; do not duplicate engine semantics |
| `python-hwpx-automation` | README, skill-first workflows, generated tool contract, product-boundary migration | Very high | **ADAPT** — generated contract, atomic workflow, dry-run/revision/idempotency, async real-Hancom queue patterns |
| `hwpx-plugins` | canonical `SKILL.md`, evidence contract, house-style routing, real-Hancom workflow, visual-review/task-eval scripts, generated host bundles | Very high | **ADOPT ARCHITECTURE** — thin skill routing, one evidence contract, generated/synchronized host bundles, explicit final-evidence gates |
| `DIVE` | README, AGENTS, constitution, decision/spec ledgers, Rust guards, MCP/provider/runtime modules, verification and human-agency features | High | **ADAPT** — evidence-before-intervention, typed boundaries, guarded execution, durable decision/evidence ledger |
| `dive-school-vibe-builder` | README, `dive-builder`/`dive-webapp` skills, references, templates, read-only harness, installer/tests | High | **ADAPT** — thin skill + references, explicit PROJECT/PLAN/AGENTS state split, read-only status/check gates |
| `EasyOCRCodex` | staged plan, modular app scaffold, batch processor | Medium | **ADAPT LESSON** — staged implementation with per-stage verification; callbacks separate progress/issues from processing |
| `MEETutorial` | tutorial-only runtime stub, agent trial assets, education folders | Low | **NOTE** — content repository can deliberately keep runtime empty; useful only as packaging discipline |
| `Bareun_Linux` | tokenizer/API experiments and minimal Flask/test files | Low | **NO DIRECT TRANSFER** |
| `AIEDAP_Bareun` | training notebook/material ordering and README execution dependencies | Low | **NOTE** — explicit prerequisite ordering in training material |
| `tutorial-test` | MakeCode extension skeleton, config, tiny runtime | Low | **NO DIRECT TRANSFER** |
| `Streamlitapp` | single-file CSV visualization prototype | Low | **REJECT FOR PRODUCTION** — useful prototype style, but deliberately too monolithic for this MCP |
| `BareunPyQt5` | Qt Designer UI assets/controller split, large generated UI surface | Low | **NOTE** — generated UI vs controller separation; no HWPX transfer |
| `assignment` | empty repository | None | **NO TRANSFER** |
| `autodiagnosis` | hard-coded Selenium flow | Negative lesson | **REJECT PATTERN** — hard-coded credentials/DOM paths and untyped browser flow are unsuitable for this product |
| `Minecraft` | recursive MakeCode/Python teaching examples | None | **NO HWPX TRANSFER** |

## Deep findings and concrete placement

### 1. Engine / application / skill ownership

Airmang's strongest architecture is not a single function. It is the three-layer ownership split:

- `python-hwpx`: generic document/package semantics.
- `python-hwpx-automation`: domain/application workflows and optional MCP adapter.
- `hwpx-plugins`: host-facing judgment and routing.

**Transfer here**

- Keep HWPX package semantics in the existing native/core modules.
- Keep page-composition metrics and mutation execution in product code, not Markdown.
- Keep `skills/hwpx-authoring/SKILL.md` responsible for archetype choice, evidence requirements, workflow routing, and escalation only.
- Never add a second Python “style engine” inside the skill bundle.

### 2. Evidence contract, not boolean success

`hwpx-plugins/references/evidence-contract.md` separates package/open safety, renderer evidence, and human visual review. `python-hwpx` similarly reports preservation and visual verification as distinct measured axes.

**Transfer here**

P3.41-R1 adds a deterministic capture adjudication layer:

`capture pack → native authority validation → per-archetype findings → cross-archetype review signals → human-review packet`.

The adjudicator must never turn page-local PDF heuristics into document identity and must never turn assistant review into user/human authority.

### 3. Mutation footprint certificate

`python-hwpx` reports changed package parts and untouched-part preservation instead of calling a write simply “safe”.

**Transfer here — successor**

P3.42/P3.43 executable layout repair should report:

- requested durable locator(s);
- expected source revision/hash;
- changed HWPX package parts;
- unexpected changed parts;
- untouched-part payload equality;
- semantic/structure hash preservation;
- native before/after render evidence when required.

This is stronger than a mutation-success boolean and aligns with the existing P3.40 localized-repair discipline.

### 4. Thin skill + references

`hwpx-plugins` and `dive-school-vibe-builder` keep the skill as a router and move detailed contracts into references. Generated host bundles are checked for drift.

**Transfer here**

- Add an explicit ownership/evidence section to the canonical HWPX authoring skill.
- Keep detailed P3.41-R1 evidence semantics in code/docs rather than duplicating them across host prompts.
- Future host-specific skill bundles should be generated from one canonical source and parity-checked, not edited independently.

### 5. State and authority separation

DIVE and DIVE Builder distinguish durable project definition, current plan/progress, runtime action, and evidence.

**Transfer here**

For benchmark/product phases maintain separate fields for:

- frozen benchmark authority;
- current implementation head;
- current regression replay;
- external/native world contact;
- assistant visual review;
- user/human sign-off.

Do not collapse these into one “PASS”.

### 6. Async real-Hancom queue

Airmang's automation MCP exposes submit/status/cancel/health instead of holding one long MCP request open.

**Transfer decision: DEFER, strong candidate**

Our current PowerShell/Windows capture bridge is sufficient for P3.41-R1. If native Hancom world contact becomes routine or multi-user, P3.42+ should consider a private worker queue with:

- input hash and idempotency key;
- worker/Hancom build identity;
- terminal receipt with artifact hashes;
- cancellation and stale-worker health;
- no promotion from preview/fake renderer to native authority.

### 7. DIVE typed guards and event evidence

DIVE's Rust runtime owns filesystem/process/network guards; UI/agent intent does not bypass them.

**Transfer here**

The same principle should govern future live Hancom automation: the skill may ask for a native action, but a typed adapter owns permitted operations, hashes, timeouts, and audit receipts. Live-host state and file-custody state remain separate.

## P3.41-R1 adoption matrix

### Adopt now

- deterministic native-capture adjudication receipt;
- cross-archetype review signals that remain review evidence, not beauty scores;
- explicit human-signoff state;
- stronger skill/runtime ownership wording;
- cross-repo harvest committed as provenance.

### Prepare next

- mutation-footprint certificate;
- canonical skill → generated host bundle parity;
- optional async/private Hancom render worker;
- pre-layout measurement and engine-authoritative geometry if Hancom exposes it;
- resource-style design-system contracts instead of expanding every tool schema.

### Reject

- duplicated style/house-style engines in skill Markdown or helper scripts;
- silent “PASS” when visual evidence is absent;
- hard-coded browser/GUI locators as product authority;
- adding languages or tools only for breadth;
- tuning frozen A3 content after observing the R1 native render.

## A3-specific lesson

The frozen A3 native capture is intentionally not repaired in place. It is evidence. If it exposes first-page underfill or macro-composition convergence across archetypes, those observations remain part of P3.41-R1 adjudication and feed successor design work rather than retroactively changing the fresh benchmark.


## Audit snapshot provenance — 2026-09-26

The exhaustive 15-repository review above is pinned to the following public default-branch heads. This is an **inspection snapshot**, not a vendored dependency lock. Later upstream changes require a new review before they are treated as adopted architecture.

| Repository | Default branch | Inspected head |
|---|---|---|
| `python-hwpx` | `main` | `0760ba978e8e0fd51f3ce578fc0c2c78a4f7e74d` |
| `python-hwpx-automation` | `main` | `8e8b95a8adff5d6a86e853a119a081c3c410512a` |
| `hwpx-plugins` | `main` | `9165a79dd94ba16416617ca5416194e6ff6110c0` |
| `DIVE` | `main` | `3493d411204e3908f717080a1f16f529c772caee` |
| `dive-school-vibe-builder` | `main` | `4829150a0d45b0b2e47fde6d81f17811f0fa9c17` |
| `MEETutorial` | `master` | `1303083a1aec7e80f84b0b7e4dfd91e44507025c` |
| `EasyOCRCodex` | `main` | `e923c98ffcf886c11a7253c938ccd0dabfcf76c7` |
| `Bareun_Linux` | `main` | `a6f1b0e5b12c791004eca6c6a949f8a39a502cf9` |
| `AIEDAP_Bareun` | `main` | `1466d432ca9b7cafb6d47f7549d1463fa502ab71` |
| `tutorial-test` | `master` | `be7e469fbf842a9ce758fe8135a39bd0fd2f5e1c` |
| `Streamlitapp` | `main` | `2a55fc1dc9d53052adf8bad58a59441a16333a0a` |
| `BareunPyQt5` | `main` | `9f2fc6f04e251493aefd622faf5cdac8fd63574b` |
| `assignment` | `main` | **empty repository** |
| `autodiagnosis` | `main` | `a43ddcd4ffc6df37e7ceb26f9f22bbe62780b431` |
| `Minecraft` | `main` | `88179bd2e13cf1b09b4a648daeb5b53957b6aa14` |

Deep-code inspection concentrated on the repositories with transferable architecture rather than mechanically reading every generated/binary asset: safe-write/product-boundary/probe contracts in `python-hwpx`; generated tool contract and workflow/render boundaries in `python-hwpx-automation`; canonical `SKILL.md`, evidence contract and bundle validator in `hwpx-plugins`; evidence-gated decision logic and QA gap ledgers in `DIVE`; and the short-skill/reference/local-harness design in `dive-school-vibe-builder`. The remaining repositories were inspected at README/root/source level and explicitly classified above as concept-only, low-priority, none, or anti-pattern rather than silently omitted.

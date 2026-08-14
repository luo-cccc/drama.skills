# Evidence-Based Review Method

## Contents

1. Independence and target freeze
2. Mechanical-before-taste pass
3. Evidence anatomy
4. Cross-layer synthesis
5. Revision and re-review
6. Anti-template review

## Rule classification

- `structural_invariant`: objectively checkable artifact integrity; validators
  may block it.
- `reviewed_invariant`: semantic integrity that requires cited evidence and an
  independent reviewer.
- `craft_default`: a recommended method that may change for a stated craft
  reason.
- `taste_option`: a creator choice that stays non-blocking unless it conflicts
  with an accepted constraint.

## Governing know-how

- `REV-01` — Run mechanical integrity checks before spending attention on taste.
- `REV-01a` — Every verdict binds the exact `.short-drama/review-bundles/*.json`
  for its target set. The lifecycle tool re-hashes the bundle, checks exact
  target equality, rejects mechanical issues, and re-runs applicable local
  checkers; an arbitrary self-reported pass JSON is not structural evidence.
- `REV-02` — Every finding names artifact/hash, bounded evidence, impact,
  required outcome, owner, severity, and status.
- `REV-03` — A semantic-invention finding pairs the authoritative source fact
  with the conflicting downstream fact; suspicion alone is not evidence.
- `REV-04` — Delivery-gate approval requires a fresh reviewer context that did
  not author the targets; stage-gate approval may come from a cold_read review
  (strict input diet in the current context) or a delta_verify closure against
  a fresh or cold base verdict (REV-12); self-check/unattested review stays
  provisional, and reviewers report and route findings but do not edit owner
  source.
- `REV-05` — Diagnose generic/repeated mechanisms at exact locations and explain
  audience or production impact instead of applying an “AI-ish” label.
- `REV-06` — Alternative preferences remain non-blocking notes unless the
  current choice violates an accepted creator constraint.
- `REV-07` — An end-to-end drafting request does not sign later artifacts;
  preview chains remain provisional, creator-pending, and delivery-blocked.
- `REV-12` — A delta_verify re-review closes a base verdict's findings against
  evidence inside the dispatched change scope; the base may be a fresh_agent or
  cold_read verdict on the identical target set, it inherits its legitimacy
  from that base, is never itself a fresh context, and escalates to a fresh
  reviewer on out-of-scope change or at the delivery gate.

## Independence and target freeze

The same context that authored an artifact may run a self-check, but it cannot
issue delivery-level approval. A reviewer starts from accepted artifacts, creator
constraints, and hashes—not the author's explanation of why the output is good.

Review spends fresh contexts only where independence pays, in three modes:

- **L1 fresh reviewer (independent agent/context)** — only for three events:
  the first review of each artifact type in a project (the type baseline), the
  delivery final gate, and after out-of-scope rewrites. Pass only the frozen
  artifact paths/hashes, accepted constraints, selected rubrics, and output
  schema. Do not pass the owner's intended fix, self-score, or an answer key.
  One fresh reviewer session may cover several scopes of the same target set;
  do not spawn one agent per scope. Record
  `requested_review_mode: independent_agent` and the actual
  `effective_review_mode`. A fresh reviewer records its runtime context ID and
  attests that it did not author any reviewed target.
- **L1.5 cold_read (current context, strict input diet)** — the default for
  routine first reviews once a type baseline exists. Read only the
  review-bundle evidence file, accepted constraints, selected rubrics, and the
  output template; do not consult the authoring reasoning, self-checks, or
  intended fixes. De-anchoring comes from input isolation, not role-play.
  Record `requested_review_mode` / `effective_review_mode: cold_read`, reviewer
  `kind: cold_reader`, `independent:false`, `provenance:null`. Cold_read
  verdicts may approve for stage progression but never open the delivery gate.
- **Self-check fallback** — when a fresh context cannot be started or the
  input diet cannot be maintained, record `self_check` or `unattested`, keep
  `independent:false`, and issue only `PROVISIONAL`; changing a role label
  inside the same context is not independence.

The deterministic project tool validates the attestation shape and bound bytes,
not the truth of host runtime identity or diet compliance; it records that
limited verification scope explicitly (`declared_provenance_structure` for
fresh reviews, `cold_read_structure` for cold reads). Host orchestration
remains responsible for actual isolation.

Freeze the review set. If a file changes during review, mark affected findings
stale and restart only the dependent scopes.

## Mechanical-before-taste pass

Scripts handle facts they can prove. They do not judge whether a scene feels
alive or an action is generally filmable.

Mechanical examples:

- missing/duplicate IDs or unresolved references;
- unknown asset variant;
- missing coverage disposition;
- explicit segments not totaling exactly the declared duration, in either direction;
- mutually exclusive structured camera flags;
- readable text with a global no-text policy;
- prompt text/hash not matching its accepted spec and recipe;
- owner writing outside its authority;
- delivery including a private path or unapproved artifact.

Semantic examples requiring review:

- downstream action changes story meaning;
- a scene has no meaningful opposition/turn;
- a keyframe prose description implies several moments;
- an untimed action load crowds out performance;
- escalation merely repeats humiliation louder;
- a prompt is specific but preserves the wrong identity.

## Evidence anatomy

A valid finding contains:

1. **Diagnostic identity:** stable catalog code, know-how rule ID, canonical
   classification, and enforcer (`validator | reviewer | creator`).
2. **Target:** artifact path, ID, hash, and field/block/shot.
3. **Evidence:** a bounded quotation or two conflicting structured facts.
4. **Impact:** what the audience, creator, continuity, or production loses.
5. **Required change:** outcome/constraint, not ghostwritten replacement prose.
6. **Owner:** the only skill allowed to make the source change.
7. **Severity/status:** and whether it blocks the requested checkpoint.

“The dialogue is weak” is invalid. “SC003 lines 12–16 repeat facts both speakers
already used as leverage, so neither agenda nor power changes before the exit;
write owner must give one speaker a costly move or cut the scene” is actionable.

The structured finding uses `target_ref` for the artifact to revise and
`evidence_refs[]` for the source/consumer sides of the conflict; do not hide a
second citation in free prose. A verdict binds exact `reviewed_artifacts`, its
`findings_ref`, reviewer-independence proof, and open-blocker count. The referenced
JSONL is authoritative for blocking-finding reconciliation: every open fatal/error
ID is listed, and every listed ID exists and is still open. Delivery may trust
approval only while those exact target and evidence hashes remain current. The
`reviewer` value is a structured object with owner, kind, explicit independence,
and the exact excluded source owner; a bare owner string is not independence
evidence and cannot issue or preserve approval.

## Cross-layer synthesis

Trace important story moves end to end. Sample questions:

- Is the promised evidence actually shown or only mentioned in a prompt?
- Does the shot preserve who knows what and who controls the prop?
- Does the keyframe depict the shot start rather than an attractive unrelated
  portrait?
- Does motion realize the accepted boundary, or invent a grab, transfer, injury,
  relationship change, or location transition?
- Does the end report reconcile with the next shot start?

Resolve upstream first. Do not polish video wording when the shot or asset binding
is wrong.

## Revision and re-review

Synthesize duplicate findings and route by owner. A revision request includes
target outcome, preserved facts, affected dependents, acceptance need, and review
scope to rerun.

Revision-scope field names are layer-specific. Review findings and video-prompt
revision proposals write `change_set` / `preserve_set`; when the target owner is
image-prompts, those same two concepts land as the edit spec's `changes` /
`preserve` (see image-prompts `edit-and-revision.md`). Same intent, different
field names — rewrite at the handoff, do not mix both spellings in one document.

Routine re-review runs as **delta verification (L2)** in the current context —
no fresh agent — provided a non-provisional base verdict (`fresh_agent` or
`cold_read`) exists for the identical target set and the revision stayed inside
the dispatched change scope:

1. freeze the new hashes and confirm the target paths match the base verdict's
   `reviewed_artifacts` exactly;
2. verify the semantic diff addresses every base blocking finding;
3. ensure preserved facts remain intact;
4. reject stale prior approval;
5. rerun exact structural and semantic dependents (REV-09);
6. close, supersede, or retain every finding explicitly;
7. confirm nothing outside the dispatched change scope or no new creative
   content appeared — otherwise stop and escalate to a fresh (L1) reviewer.

The delta verdict records `requested_review_mode` and `effective_review_mode`
as `delta_verify`, binds its base in `delta_basis` (base review id, verdict ref
and hash), and names the verifier as `kind: delta_verifier` with
`independent:false`; approval legitimacy is inherited from that base (fresh or
cold) plus the evidence-checked closure, never from the delta context itself.
The delivery final gate always escalates to L1.

## Anti-template review

Do not use a banned-word list as a quality verdict. Look for mechanisms:

- every episode uses the same hook/turn/cliffhanger with renamed nouns;
- all characters share sentence length, vocabulary, and emotional escalation;
- action paragraphs stack abstract intensity without playable behavior;
- prompts lead with generic quality adjectives and bury identifying facts;
- every line gets an unnecessary reaction close-up;
- camera movement is used as decoration rather than attention or power;
- repeated boilerplate contradicts the specific scene.

Cite locations and impact. Preserve deliberate genre rhythm and creator choices.

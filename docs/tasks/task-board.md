# CadFlow Task Board

## Done

- [x] Define canonical Workspace / Work / Run / Part Job architecture.
- [x] Add Current Work active-lineage view and immutable Run Snapshot.
- [x] Unify Workflow graph, selected-stage detail, artifact contracts, and action targets in the v2 page view model.
- [x] Implement Candidate Detail and explicit `Use This Part Next` with validated Assembly Plan override.
- [x] Add downstream stale projection while preserving old Runs and accepted results.
- [x] Add append-only Stage Reviews and Work-level accepted part-result pointers.
- [x] Add persistent action pending/success/failure lifecycle and selected postcondition verification.
- [x] Add bounded deterministic `create_part_ir` Episode and scripted dynamic action tests.
- [x] Consolidate current architecture documents and remove superseded milestone architecture.
- [x] Define logical agents, skills, shared knowledge, skill-private knowledge, Work context, and Run observations.
- [x] Separate accepted input, execution, result, agent review, user approval, and capability-mode state.
- [x] Isolate CAD candidate execution and remove product-positioned model files after terminal validation failure.
- [x] Restrict Work Deliverables to explicit approved `accepted_part_results`; keep unapproved outputs reviewable.

## Current — Workflow Cockpit usability gate

- [x] Define bilingual Guidance Contract fields and move default audit/action metadata to expandable Action Details / Advanced.
- [ ] Click every visible enabled action in a real browser and record PASS/FAIL.
- [ ] Verify Chinese labels, Hover, dialogs, validation, pending, success, failure, and disabled reasons.
- [ ] Verify at least one deliberate action failure and recovery path.
- [ ] Complete the stale -> rebuild -> Part Result Review -> user approval Full Golden journey.
- [ ] Verify Contract Golden does not offer STEP/STL or part-result approval and does not appear blocked.
- [ ] Complete 1024px responsive acceptance.
- [ ] Capture current desktop, candidate, review, failure, Snapshot, 1024px, and mobile screenshots.
- [ ] Store release acceptance evidence outside the product artifact tree, with scenario and viewport metadata.
- [ ] Mark Workflow Cockpit MVP usable only after the manual gate passes.

### Navigation and guidance acceptance follow-up

- [x] Restore Work → Workflow navigation with an event-safe page callback and strict page-id contract.
- [ ] Recapture valid Chinese Guidance evidence after the current semantic and navigation changes.
- [ ] Select and verify the Contract Golden flow, Run Snapshot, and 390–430px layout before closing the usability gate.

## Next — Typed Skill and Knowledge Registry

- [ ] Define typed skill metadata: skill id, logical role, checkpoint, operations, contracts, context keys, tools, and stop reasons.
- [ ] Define knowledge registry metadata: id, owner, layer, source, version, and allowed skills.
- [ ] Enforce shared versus skill-private knowledge access.
- [ ] Remove duplicate inline skill/knowledge sources from provider context assembly.
- [ ] Fail fast on missing, duplicate, or unauthorized skill/knowledge definitions.
- [ ] Add selected skill and knowledge ids to safe episode/provider traces.
- [ ] Keep deterministic Agent Adapter and Golden outputs stable.

## Later

- [ ] Prototype provider-backed bounded `create_part_ir` after both gates above.
- [ ] Add user-facing Run comparison details.
- [ ] Expand structured inline interventions where canonical checkpoints require them.
- [ ] Add Agentic Planning candidates and Requirement clarification episodes.
- [ ] Add multiple Part Job progression before any full assembly claim.
- [ ] Add Assembly Agent execution only after accepted sibling part results and deterministic assembly validation exist.

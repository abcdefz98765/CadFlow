# CadFlow Current Milestones

## Completed architecture foundations

- Canonical Workspace / Work / Run / Part Job model and checkpoint responsibilities.
- Current Work active-lineage projection and immutable Run Snapshot boundary.
- Reviewed single-part artifact flow through CAD IR validation and deterministic Contract/Full execution.
- Work-level accepted part-result pointers and append-only Stage Reviews.
- Provider-independent bounded `create_part_ir` episode shell with dynamic scripted action tests.
- Canonical Agent, Skill, and Knowledge ownership model.

Completed here means implemented or documented with automated coverage where applicable. It does not imply complete browser usability or provider-backed agentic CAD.

## Current milestone — Workflow Cockpit usability acceptance

Implemented and automated-tested:

- v2 Workflow rendering path;
- Candidate Detail and explicit candidate selection;
- validated Assembly Plan override and stale projection;
- controlled artifact viewers;
- append-only Stage Review;
- write-action lifecycle and persistent feedback;
- primary Workflow Chinese/English catalog coverage;
- Contract versus Full semantics.

Acceptance still required:

- real-browser click-through of every visible enabled action;
- confirmed pending, success, failure, and recovery behavior;
- complete Chinese primary Workflow review;
- 1024px responsive acceptance;
- full stale-to-rebuilt-to-approved Golden journey;
- current screenshots.

Do not mark the Workflow Cockpit MVP usable until this gate passes.

## Next milestone — Typed Skill and Knowledge Registry

Replace duplicated static runtime skill/knowledge definitions with one typed registry declaring:

- logical skill and operation mapping;
- canonical checkpoint and artifact contracts;
- allowed context keys and tools;
- shared knowledge ids;
- skill-private knowledge ids;
- stop reasons and capability mode;
- source provenance.

Required outcomes:

- missing or duplicate definitions fail fast;
- operations cannot access another skill's private knowledge;
- runtime provider context and repository skill docs cannot silently diverge;
- selected skill/knowledge ids appear in safe traces;
- existing deterministic tests remain stable.

This milestone does not add a provider or CAD family.

## Following milestone — Provider-backed bounded CAD IR prototype

Connect one provider-backed proposer only for `create_part_ir`.

Initial actions:

- request allowlisted context;
- submit structured CAD IR;
- ask the user;
- repair from validator observations;
- stop with typed outcome.

The same CAD IR validators and deterministic pipeline remain authoritative. No provider-generated Python, shell, or direct CadQuery execution is allowed.

## Later milestones

- Agentic Planning candidate episode.
- Requirement clarification episode.
- Multiple Part Job progression.
- Assembly placement and validation only after multiple accepted part results exist.
- Broader revision and comparison experience.

Full assembly generation, batch CAD, motion/strength/fit validation, and external-CAD feature recovery remain separate future capabilities.
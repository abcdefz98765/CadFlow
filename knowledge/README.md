# Shared Knowledge

This directory contains only knowledge that is genuinely shared by more than one CadFlow skill.

Read:

- `../docs/architecture/agent-skill-knowledge.md`

## What belongs here

Examples:

- cross-skill CAD IR vocabulary;
- shared units and naming references not already owned by policy;
- interface vocabulary used by Planning, CAD IR, Assembly, and Review;
- common manufacturing references needed by multiple skills.

A shared source has one owner and one version. Do not copy separate variants into several skill directories.

## What does not belong here

Skill-private knowledge stays under:

- `skills/requirement/knowledge/`;
- `skills/planning/knowledge/`;
- `skills/cad_ir/knowledge/`;
- `skills/part_modeling/knowledge/`;
- `skills/assembly/knowledge/`;
- `skills/review/knowledge/`;
- `skills/revision/knowledge/`.

Global invariants and safety rules belong in `policies/`, not in knowledge files.

Accepted Work artifacts, selected candidates, reviews, and prior results are runtime context selected from the active lineage. Validator feedback and repair attempts are Run/episode observations. Neither category should be copied into static knowledge.

## Runtime selection

Provider or proposer requests receive only selected compact summaries declared by the current skill. They must not receive the whole knowledge tree, arbitrary files, secrets, raw logs, or provider transcripts.

When a skill-private reference becomes necessary to multiple skills, promote it to a shared source and update the skill/knowledge registry rather than duplicating it.
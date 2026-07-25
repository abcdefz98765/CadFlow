# Shared Knowledge

This directory contains engineering knowledge genuinely shared by multiple
CadFlow skills.

Suitable examples include units and naming, feature-graph vocabulary, interface
and datum semantics, manufacturing references, fastener/component standards,
and evaluation terminology.

Each shared source has one owner and version. Skill-private heuristics stay
under `skills/<skill>/knowledge/`; global safety and trust rules stay in
`policies/`.

Accepted Work artifacts, candidate geometry, reviews, validator feedback, and
repair attempts are runtime context or observations, not static knowledge.

The Context Broker supplies only the compact, allowlisted knowledge declared by
the active skill. It never loads the whole knowledge tree, arbitrary files,
secrets, raw logs, or provider transcripts.

See `../docs/architecture/agent-skill-knowledge.md`.

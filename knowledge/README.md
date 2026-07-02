# Knowledge

Top-level knowledge is an index for shared, cross-skill references.

Step-specific knowledge should live under the owning skill:

- requirement knowledge: `skills/requirement/knowledge/`
- part modeling knowledge: `skills/part_modeling/knowledge/`
- assembly knowledge: `skills/assembly/knowledge/`
- review knowledge: `skills/review/knowledge/`

Keep this directory lightweight. Add global knowledge only when multiple skills
need the same source of truth.

Provider requests should not include the whole knowledge tree. The provider
context assembler should select a compact global summary plus stage-specific
knowledge only when it is relevant to the current operation.

See `docs/architecture/agent-skill-knowledge.md` for the agent/skill/knowledge
context design.

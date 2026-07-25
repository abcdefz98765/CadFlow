# Intent Artifact Template

Target semantic shape:

```json
{
  "objective": "what should be designed and why",
  "scope": "part | multi_part | assembly | exploratory",
  "functions": [],
  "dimensions": [],
  "interfaces": [],
  "manufacturing_intent": {},
  "evaluation_targets": [],
  "deliverable_intent": [],
  "assurance_mode": "explore",
  "user_facts": [],
  "agent_assumptions": [],
  "missing_decisions": [],
  "focused_questions": [],
  "source": {},
  "revision": {}
}
```

The schema may evolve, but it must preserve the semantic separation between user
facts, Agent assumptions, missing decisions, and evidence expectations.

Current `requirement.json` fields such as `part_type`, `features`, `outputs`,
`check_level`, and `cad_brief` are compatibility fields for the legacy prompt
and CAD IR pipelines. They may be projected from Intent but must not define the
target design space.

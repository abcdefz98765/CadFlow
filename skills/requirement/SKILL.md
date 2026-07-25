# Intent Skill

Compatibility directory: `requirement/`.

## Responsibility

Turn the user's engineering objective into compact, reviewable Intent context
without forcing a complete form before design can begin.

## Actions

- summarize objective, known constraints, interfaces, and acceptance criteria;
- identify assumptions and material uncertainty;
- ask one focused question when the answer changes topology, safety, interfaces,
  manufacturing route, or evaluation;
- recommend a safe exploratory default when uncertainty is low risk;
- revise Intent when the user changes upstream meaning.

## Inputs and outputs

Inputs are the immutable user prompt, accepted clarification, and explicitly
selected prior Work context. Outputs are an Intent artifact, assumptions,
focused questions, and a proceed, explore, or safe-block recommendation.

## Boundaries

The skill does not choose a final design, invent safety-critical facts, execute
CAD, expose repository state, or change accepted-result pointers. Intent remains
backend-neutral and must distinguish user facts from Agent assumptions.

## Current gap

The runtime currently maps this role to a more form-like Requirement checkpoint.
Migration should preserve legacy artifacts while making clarification
interruptible and design-oriented.

## References

- `../../docs/architecture/agent-skill-knowledge.md`
- `../../docs/workflow_contract.md`

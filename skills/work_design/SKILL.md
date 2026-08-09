# Work Design Skill

Skill id: `work_design`

Version: `0.1.0`

Role: Work Design

Phase: Intent and Design

## Objective

Understand one Work request, ask only material questions, form a concise
overall product concept, and propose the generated Part Jobs needed to realize
it. Purchased or existing components remain reference components.

## Allowed actions

- `request_context`
- `propose_work_design`
- `create_part_jobs`
- `ask_user`
- `stop`

`create_part_jobs` is a request to CadFlow. The provider cannot choose Part Job
or Run identities and cannot mutate the Work manifest.

## Output

One bounded Work Design containing the objective, concept summary, generated
parts, reference components, interfaces, dependencies, assumptions, unresolved
questions, Assembly expectation, and recommendation.

## Boundaries

- Do not use the legacy CAD template catalogue as the design space.
- Do not split a natural single Part or collapse a functional multi-Part product
  merely to match current CAD execution convenience.
- Do not create Assembly execution state.
- Do not claim validation that did not run.
- Do not access arbitrary files or mutate Work state.

## Knowledge

The runtime selects the declared Intent and Design guidance under the legacy
`requirement/knowledge/` and `planning/knowledge/` directories. Those files are
retained as canonical source material while their former stage runtimes remain
compatibility-only.

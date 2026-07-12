# Generic-Family CAD IR

CadFlow should not require one CAD template for every domain-specific part
name. Names such as `upper_link` and `lower_link` describe source intent and
assembly roles; they are not backend geometry types.

The reviewed-part path keeps that intent while asking the agent for a CAD IR:

```text
reviewed_part_handoff.json
-> AgentAdapter.create_part_ir(...)
-> generic-family normalization attempt
-> CAD IR validation
-> generation or a traceable validation block
```

For the current link-like example, the normalized contract is:

```yaml
source_part_id: upper_link
source_intent: upper_link
part_type: link_like_part
geometry_family: elongated_plate_with_end_holes
```

`source_part_id` and `source_intent` preserve the domain-specific meaning.
`part_type` selects the reusable CAD IR family, while `geometry_family`
identifies its backend-neutral geometric representation. The normalization
trace records the source, destination, and mapping reason.

## Templates and primitives

Templates and primitives are guardrails and bootstrap mechanisms. They provide
validated shapes, safe parameter boundaries, and deterministic execution where
appropriate. They must not become a requirement that every new part name has a
dedicated template, and they must not prevent agent-driven CAD IR synthesis.

An unknown part must not terminate merely because no same-named template
exists. It should reach `AgentAdapter.create_part_ir(...)`, receive a generic
family normalization attempt, and then pass through validation and reporting.
It must never be silently replaced with an unrelated supported family.

If normalization is not possible, the reviewed-part workflow should return
`blocked_cad_ir_validation`. It should preserve `cad_ir_draft.json`, the
failure diagnostics, and the agent trace so the capability boundary remains
reviewable. Provider-generated CadQuery or Python must not bypass CAD IR.

If generation succeeds, its scope remains `single_generic_concept_part`.
Successful STEP/STL output proves only that one normalized concept part was
generated. It does not mean the source assembly, all assembly parts, fit,
motion, or strength have been validated.

See the static summaries in
`examples/reviewed_part_generic_link_like/` for both `upper_link` and
`lower_link`. They intentionally use the same generic family.

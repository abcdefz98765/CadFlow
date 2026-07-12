# Negative Example: No Template Fallback

This document lists outcomes that violate the reviewed-part and generic-family
CAD IR architecture. They are failure cases, not supported shortcuts.

- `upper_link -> mounting_plate`: unrelated-family fallback loses intent and
  creates misleading geometry.
- `upper_link -> upper_link_template`: a domain-specific template bypasses the
  reusable generic-family boundary.
- `no template -> terminal block before AgentAdapter.create_part_ir`: absence
  of a same-named template must not prevent the normalization attempt.
- Provider-generated CadQuery or Python bypasses CAD IR: executable provider
  output must not skip local CAD IR validation and reporting.
- Successful STEP/STL reports a full robot-arm assembly: a reviewed-part run
  generated only one `single_generic_concept_part`.

If the agent cannot map an intent to a supported generic family, the correct
result is `blocked_cad_ir_validation` with a retained `cad_ir_draft.json` and
failure trace. Substituting `mounting_plate`, inventing a part-specific
template, or claiming assembly completion is not an acceptable fallback.

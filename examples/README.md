# CadFlow Examples

Examples are classified by purpose. Files under `examples/` are not all
user-facing product examples, and passing one category does not prove another.

## PRODUCT GOLDEN

| Example | Purpose | Current product behavior |
| --- | --- | --- |
| `canonical_product_golden/` | Reproducible current Agent-first single-Part Job story | Yes. Open it from Workspace with **Open Product Example**. It uses a scripted provider, the registered model-program path, controlled execution, STEP inspection, reviewable publication, and the existing Accept/Revise routes. |

The Product Golden proves the product journey, durable projection, Workbench,
geometry presentation, and acceptance/revision behavior. It does not prove
external-provider design quality. It requires no external API credential.

## BENCHMARK / EVALUATION

| Example | Purpose | Product claim |
| --- | --- | --- |
| `provider_smoke/parse_requirement_smoke.py` | Real-provider JSON contract check | Provider evaluation only. |
| `provider_smoke/create_workflow_smoke.py` | Real-provider legacy Requirement/Planning boundary | Compatibility evaluation only. |
| `provider_smoke/provider_create_eval.py` | Curated provider-create cases | Evaluation only; not general CAD coverage. |
| `provider_smoke/normalized_design_eval.py` | Normalized provider design cases | Evaluation only; assembly prompts stop at planning. |
| `provider_smoke/reviewed_part_single_create_smoke.py` | Staged legacy reviewed-one-part boundary | Compatibility evaluation; never full assembly. |
| `prompt_pipeline/` | Manual deterministic prompt-to-IR evaluation | Compatibility evaluation. |

The later five-case external-provider benchmark will assess real Agent design
quality, strategy, repair, and `ask_user` behavior. It is intentionally not the
Product Golden and is not run by M2.6.

## COMPATIBILITY / REGRESSION

| Example | Purpose | Current status |
| --- | --- | --- |
| `golden_desktop_robot_arm/` and `scripts/run_golden_desktop_robot_arm.py` | Former Requirement/Planning/reviewed-part/CAD IR Golden | Preserved regression and multi-part planning evidence. It is not the primary product example and does not generate a complete robot arm or Assembly Job. |
| `reviewed_part_generic_link_like/` | Generic-family reviewed-part normalization fixtures | Historical compatibility evidence. |
| `workflow_console/` | Static schema-v1 Work templates for legacy console states | Compatibility fixtures, not the Product Golden. |
| `ir_pipeline/` | Deterministic closed-family CAD IR executor fixtures | Regression coverage for the compatibility pipeline. |
| `parts/` | Standalone CadQuery model scripts | Historical model regression/demo assets. |
| `assemblies/enclosure/` and `assemblies/pet_button/` | Disconnected assembly intent, placement, and validator demos | Historical/internal; not executable canonical Assembly Jobs or Deliverables. |
| `workflow/mounting_plate_demo.py` | Former workflow orchestration demo | Compatibility regression. |
| `negative_no_template_fallback/` | Negative architecture assertions | Regression evidence that unrelated templates must not replace intent. |

## INFRASTRUCTURE SMOKE

| Example | Purpose | Product claim |
| --- | --- | --- |
| `provider_smoke/tool_broker_gate_eval.py` | Tool Broker authority and fail-closed capability gate | Infrastructure boundary only. |
| `provider_smoke/work_design_episode_eval.py` | Owned Part Job episode persistence and replay | Infrastructure route only; no geometry. |
| `provider_smoke/model_program_policy_eval.py` | CadQuery v1 static source policy | Static policy only; no execution. |
| `provider_smoke/model_program_episode_eval.py` | Attested WSL2 model-program episode | Internal execution acceptance, not publication. |
| `provider_smoke/reviewable_product_route_eval.py` | Reviewable publication plus explicit Accept/Revise authority | Current-host infrastructure/product-route smoke in a temporary Workspace. |

Generated files remain ignored unless a fixture explicitly states otherwise.
Useful regression fixtures are retained even when their original UI journey is
no longer the canonical product experience.

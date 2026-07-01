# Product Positioning

CadFlow is an AI-assisted natural-language CAD workflow system.

CadFlow is natural-language first for users and structured-workflow first internally. Users describe CAD intent in plain language, while CadFlow converts that intent into auditable requirement, planning, CAD IR, generation, validation, repair, and review artifacts.

The default user experience should be natural language first. Internal workflow artifacts are visible for transparency, but users should not need to understand them to generate a model.

## CadFlow Is

- An AI-assisted natural-language CAD workflow system.
- A workflow-first CAD agent scaffold.
- A STEP-first parametric CAD generation pipeline.
- A system for traceable CAD generation, validation, repair, and review.

## CadFlow Is Not

- A browser CAD editor.
- A mesh generation system.
- A prompt-to-STL toy.
- A production-ready CAD engineer replacement.
- A full FreeCAD or SolidWorks replacement.
- A cloud SaaS platform in the current stage.

## Product Boundary

CadFlow separates understanding, deterministic execution, and review:

- LLM/Agent: understanding, planning, repair advice, and explanations.
- CadFlow Python API: deterministic execution through validated contracts.
- Web UI: operation, visualization, artifact review, and trace inspection.
- CadQuery/STEP: CAD backend and artifact output.

The user should not manually write CAD IR or operate the requirement, planning, and IR stages during the default workflow. Those artifacts exist for audit, debugging, review, and advanced inspection.

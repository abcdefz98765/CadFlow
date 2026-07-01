# Product Positioning

CadFlow is an AI-assisted natural-language CAD workflow system.

CadFlow is natural-language first for users and structured-workflow first internally. Users describe CAD intent in plain language, while CadFlow converts that intent into auditable requirement, planning, CAD IR, generation, validation, repair, and review artifacts.

The default user experience should be natural language first. Internal workflow artifacts are visible for transparency, but users should not need to understand them to generate a model.

CadFlow's product direction is iterative CAD workflow, not one-shot
Text-to-CAD. Users often do not know complete requirements at the beginning, and
many workflows should start from an existing generated or imported model. The
system should support unclear intent, explicit assumptions, exploratory drafts,
focused confirmation, revision prompts, child runs, and old/new comparison.

## CadFlow Is

- An AI-assisted natural-language CAD workflow system.
- A workflow-first CAD agent scaffold.
- A STEP-first parametric CAD generation pipeline.
- A system for traceable CAD generation, validation, repair, and review.
- A future iterative model revision workflow for CadFlow-native runs and limited
  external reference geometry.

## CadFlow Is Not

- A browser CAD editor.
- A mesh generation system.
- A prompt-to-STL toy.
- A production-ready CAD engineer replacement.
- A full FreeCAD or SolidWorks replacement.
- A cloud SaaS platform in the current stage.
- A robust STEP feature-recovery engine.
- A parametric reverse-engineering system for STL or OBJ meshes.

## Product Boundary

CadFlow separates understanding, deterministic execution, and review:

- LLM/Agent: understanding, planning, repair advice, and explanations.
- CadFlow Python API: deterministic execution through validated contracts.
- Web UI: operation, visualization, artifact review, and trace inspection.
- CadQuery/STEP: CAD backend and artifact output.

The user should not manually write CAD IR or operate the requirement, planning, and IR stages during the default workflow. Those artifacts exist for audit, debugging, review, and advanced inspection.

## Requirement Uncertainty

CadFlow should not require perfect up-front requirements for low-risk
exploration. For L0 Playground and some early L1 Maker workflows, it may proceed
with explicit assumptions. Those assumptions must be written into artifacts,
shown to the user, and available for later revision.

For L2/L3/L4 workflows, CadFlow must not silently invent engineering-critical
details. Material, load, tolerance, safety, fit, and certification fields should
block or require focused confirmation when missing.

## Revision Positioning

The first revision workflow should prioritize CadFlow-native parent runs because
they preserve requirement, planning, IR, source, validation, report, and trace
artifacts. Revisions should create child runs with structured patches and
lineage instead of overwriting the parent.

External STEP files are useful as reference geometry but usually lack full
modeling history. STL and OBJ files should be treated as mesh references, not
reliable editable CAD sources.

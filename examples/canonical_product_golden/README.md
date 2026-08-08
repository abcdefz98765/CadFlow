# Canonical Product Golden: Compact Micro Servo Mounting Bracket

Classification: **PRODUCT GOLDEN**.

This is the reproducible current-product example for the Agent-first Workbench.
Open the Workspace page and choose **Open Product Example**. CadFlow creates or
reopens the Work and navigates directly to Overview / Design.

## Original request

> Create a compact single-piece mounting bracket for a micro servo. It should
> mount to a flat panel with four screws, support the servo between two upright
> ears, and leave cable clearance. Choose sensible prototype dimensions. This
> is an exploration model, not a strength-validated release part.

The prompt fixes purpose and interfaces while leaving dimensions and geometry
strategy to the Agent.

## Reproducible journey

```text
natural-language request
  -> Work
  -> servo_mounting_bracket Part Job
  -> scripted design_part Episode
  -> persisted design brief and cadquery_v1 candidate
  -> attested controlled execution
  -> STEP geometry and re-import inspection
  -> reviewable result
  -> Workbench presentation
  -> explicit Accept or Revise
```

The example uses a scripted provider and requires no external API credential.
Candidate source still passes through the registered model-program policy,
attested Tool Broker execution, geometry inspection, and reviewable publication
gate. If that execution profile is unavailable, the action fails closed and
reports recovery; it never falls back to unrestricted host execution.

## What it proves

- the current product journey and durable Work/Run/Part Job projection;
- direct visibility of original input and concise persisted Agent design;
- the existing STL viewer over a registered reviewable STEP;
- measured geometry and honest verified/assumed/unverified/unsupported scope;
- the compact Overview-to-Detailed-Workflow relationship;
- explicit acceptance and revision with preserved history.

It does not prove external-provider design quality, general CAD capability,
manufacturer servo fit, strength, tolerance, motion, Assembly Job execution, or
engineering release readiness. The example is deliberately left reviewable and
unaccepted when first opened.

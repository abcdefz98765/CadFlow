# Project PRD Index

Current product requirements:

- `../FINAL-PRD.md` — concise current product baseline;
- `../PRD_new.md` — detailed current product requirements;
- `../architecture/cadflow-canonical-product-architecture.md` — authoritative object model and checkpoint responsibilities;
- `../workflow_contract.md` — artifact, trust-state, review, and delivery contracts;
- `../status/current-product-readiness.md` — honest implementation and verification status;
- `../roadmap/milestones.md` — current milestone order.

Historical phase and version documents under `docs/project/` are implementation
history. They do not override the sources above.

Current direction:

```text
accepted engineering intent
  -> reviewed structured CAD contract
  -> isolated deterministic execution
  -> validated reviewable result
  -> explicit user approval
  -> accepted Work deliverable
```

File presence is not approval. Failed attempts retain diagnostic evidence but
do not publish product-positioned CAD files. Contract mode validates the
contract and intentionally skips STEP/STL execution.

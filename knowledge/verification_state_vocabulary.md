# Verification-State Vocabulary

Use exactly these evidence states when describing a result or engineering
claim:

- `verified` — a declared local check ran and passed for the stated claim.
- `measured` — a tool reported the stated observed value or geometry property.
- `assumed` — a visible design input was selected without local verification.
- `unverified` — the claim has not been established by a local check or
  measurement.
- `unsupported` — the current declared capability cannot establish or perform
  the requested claim or operation.
- `not_requested` — the user did not request the check, measurement, or claim.

These evidence states are independent of product trust state. A `candidate` is
untrusted proposed input or execution evidence. `reviewable` means a locally
validated `reviewable_result` is available for user review. `accepted` means
CadFlow has an explicit accepted-result pointer to that exact result.

`candidate` is not `reviewable`, and `reviewable` is not `accepted`. Execution,
validation, publication, or file presence never creates acceptance.

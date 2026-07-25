# Design Routing Guidance

Routing selects the next useful Agent action, not a mandatory stage sequence.

Possible actions include:

- inspect Intent or accepted interface context;
- propose or compare concepts;
- create or revise a Part Job;
- create or revise an Assembly Job;
- build a structured geometry candidate;
- build a sandboxed model-program candidate;
- request Evaluation;
- ask one focused question;
- stop with a typed safe reason.

Choose actions by expected information gain, design risk, and user value.
Internal artifacts record the decision but do not become a user-facing wizard.

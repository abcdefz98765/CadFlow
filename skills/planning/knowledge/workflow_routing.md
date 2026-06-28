# Workflow Routing

Planning selects the next workflow route from the requirement package.

## Routes

- `single_part`: one manufacturable part can satisfy the request.
- `multi_part`: multiple generated parts are needed, but no assembly placement
  is required yet.
- `assembly`: generated parts and reference components need relationships,
  clearances, contacts, or service access.
- `confirmation_needed`: a topology-changing decision is missing.

## Routing Guidance

- Use `single_part` for simple plates, brackets, spacers, and covers with no
  moving or installed components.
- Use `assembly` when the request includes moving parts, electronics, sensors,
  wiring, replaceable components, fasteners, or serviceability.
- Use `confirmation_needed` when choosing a route would require guessing switch
  type, sensor envelope, fastening style, wire direction, removable vs sealed
  behavior, or another topology-changing interface.

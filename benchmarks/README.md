# CAD Benchmarks

Phase 1.9 benchmarks are deterministic IR-first regression cases for the CAD
Agent Loop. They are intended to catch geometry, artifact, validation, and trace
regressions without parsing natural language directly into code.

Run locally:

```powershell
$env:PYTHONPATH='src'; .venv-cadflow\Scripts\python.exe -m ai_native_cad.benchmarks.runner
```

Benchmark outputs are written to `outputs/benchmarks/`, including
`benchmark_summary.json`.

Current scope:

- mounting plate with four verified through holes
- spacer / washer
- simple L-bracket
- simple enclosure base
- mounting plate repair case that must record an IR repair diff

`circular_flange` is a planned benchmark once that part type has a supported IR,
generator, and validation contract.

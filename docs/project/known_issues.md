# Known Issues & Limitations

## Constraint Assembly (v0.3)

### C-001: Coincident constraint assumes specific face pair
**File:** `scripts/freecad_constraint_assembly.py:_constraint_coincident`
**Severity:** Low
**Status:** Won't fix in v0.3

The coincident constraint always mates `obj1`'s bottom face (ZMin) to `obj2`'s top face (ZMax). A proper implementation requires selecting specific faces by name/index, which needs a face-picking API not feasible with the current bbox-based approach. Users needing arbitrary face pairing should use absolute positioning or FreeCAD's GUI constraint solver.

### C-002: Concentric constraint uses CenterOfMass approximation
**File:** `scripts/freecad_constraint_assembly.py:_constraint_concentric`
**Severity:** Low
**Status:** Won't fix in v0.3

The concentric constraint aligns part centers of mass, not cylindrical faces. This works correctly for rotationally symmetric parts (spacers, bushings) but may produce incorrect alignments for asymmetric parts with off-center COMs. True cylindrical face alignment requires face selection.

### C-004: Interference check unreliable with imported STEP geometry
**File:** `scripts/freecad_constraint_assembly.py:_check_interference`
**Severity:** Medium
**Status:** Known (threshold raised to 300mm³)

FreeCAD's `Shape.common()` boolean intersection on imported STEP solids reports false-positive interferences even with explicit clearance gaps (tested with 0.5mm+ gaps). This appears to be a precision/tolerance artifact in FreeCAD's solid kernel when operating on imported geometry. Visual verification in FreeCAD GUI should be the primary validation method. The checker is disabled by default in assembly configs (`check_interference: false`).

### C-003: Parallel/Distance constraints are bbox-based approximations
**File:** `scripts/freecad_constraint_assembly.py:_constraint_parallel`, `_constraint_distance`
**Severity:** Low
**Status:** Won't fix in v0.3

These constraints use bounding box extents rather than actual face geometry. This produces correct results for rectangular parts but may be imprecise for irregular shapes. Full face-based constraint solving is deferred to future FreeCAD Assembly4 integration.

---

## Validator (v0.1)

### V-001: Dimension failures now affect valid flag (resolved v0.4)
**File:** `src/ai_native_cad/validator.py`
**Severity:** Low
**Status:** Fixed

Failing dimension checks (e.g., `expected=80, actual=100`) now DO flip the top-level `valid` flag to `false`. Same for zero/negative volume checks. The validator is authoritative: if any check fails, `valid` is `false`.

### V-002: Dimension map only covers principal axes
**File:** `src/ai_native_cad/validator.py:dim_map`
**Severity:** Low
**Status:** By design

The validator can only check dimensions that map 1:1 to bounding box axes (`length→X`, `width→Y`, etc.). Composite dimensions (e.g., `arm_height` for a bracket, `outer_height` for enclosure with bosses) cannot be validated against the overall bbox. Dimensions not in the map are silently skipped.

---

## FreeCAD Handoff API (v0.2)

### H-001: Screenshot only available in GUI mode
**File:** `src/ai_native_cad/freecad_handoff.py`
**Severity:** Low
**Status:** By design (guarded with `FreeCAD.GuiUp`)

Screenshot generation requires `freecad.exe` (GUI mode). When running under `freecadcmd.exe` (headless), screenshots are skipped with a warning. The standalone script `scripts/freecad_handoff.py` does not attempt screenshots for this reason.

### H-002: API module vs standalone script confusion
**File:** `src/ai_native_cad/freecad_handoff.py` vs `scripts/freecad_handoff.py`
**Severity:** Low
**Status:** Known

The project ships two paths for FreeCAD handoff:
- `scripts/freecad_handoff.py` — standalone, run with `freecadcmd.exe`, no package imports
- `src/ai_native_cad/freecad_handoff.py` — API module, importable from the package, requires FreeCAD installation

The API module is primarily for environments where FreeCAD is installed and importable from the same Python. The standalone script is the recommended path for most users.

### H-003: No FCStd auto-generation without FreeCAD installed
**Status:** Expected limitation

FreeCAD operations (FCStd save, TechDraw, assembly) require a FreeCAD installation on the host machine. The CadQuery pipeline works independently.

---

## Architecture Gaps (all versions)

### A-001: Dual execution path — standalone `main()` vs `runner.run_part()` (RESOLVED)
**Files:** `examples/*/model.py` vs `src/ai_native_cad/runner.py`
**Severity:** Medium
**Status:** Fixed in v0.4

All four examples now import from the core library (`ai_native_cad.exporter`, `ai_native_cad.validator`, `ai_native_cad.report`). Standalone `main()` functions resolve `sys.path` to import the package, then delegate export, validation, and report generation to the same library functions used by `runner.run_part()`. The prompt template has been updated to teach agents this pattern.

### A-002: No `list_parts()` introspection for agents (RESOLVED)
**File:** `src/ai_native_cad/generator.py`
**Severity:** Low
**Status:** Fixed in v0.4

Added `list_parts()` returning `["enclosure_base", "enclosure_lid", "spacer", "wall_bracket"]`. Agents can now programmatically discover available part types.

### A-003: Asymmetric report generation — some examples skip `report.md` (RESOLVED)
**Files:** `examples/*/model.py`
**Severity:** Low
**Status:** Fixed in v0.4

All four examples now call `generate_report()` from `ai_native_cad.report`, which always writes both `report.json` and `report.md`. The output is consistent across all entry points (standalone `main()`, `runner.run_part()`, and the core library).

### A-004: Placeholder preview image in CadQuery pipeline
**Severity:** Medium
**Status:** Open / deferred from Phase 1.8

The CAD Agent Loop writes `preview.png`, but it is currently a visible placeholder image, not a rendered geometry snapshot. The earlier 1x1 black placeholder has been replaced with a readable scaffold image so downloaded previews do not look like broken renders. Phase 1.8 now records STEP-first inspection facts and trace summaries, while real preview rendering remains deferred because this slice should not introduce Blender, FreeCAD automation changes, or heavy rendering dependencies. Evaluation complete: recommended path is a lightweight three.js STL viewer (`web-viewer/index.html`) with optional trimesh-based glTF/GLB export. See `docs/web_preview.md` for full evaluation. FreeCAD screenshots remain GUI-only.

**Recommendation:** Implement `web-viewer/index.html` prototype, then optionally add GLB export to the pipeline if the dependency tradeoff remains acceptable.

### A-005: Hardcoded output paths in examples depend on `cwd` (RESOLVED)
**Files:** `examples/*/model.py`, `src/ai_native_cad/runner.py`
**Severity:** Low
**Status:** Fixed in v0.4

Examples now delegate output placement to `runner.py`. When an example script is executed directly, generated artifacts are written next to that script's `model.py`; user workflow runs should pass an explicit `output_dir` and otherwise fall back to `runs/<instance_name>/`.

### A-006: No CI configuration (RESOLVED)
**Severity:** Medium
**Status:** Fixed in v0.4

Added `.github/workflows/test.yml` running pytest on Ubuntu (Python 3.10, 3.11, 3.12) and Windows (Python 3.10) on push/PR to master/main.

### A-007: `freecad_handoff.py` API module has unclear role
**File:** `src/ai_native_cad/freecad_handoff.py`
**Severity:** Low
**Status:** Documented (see H-002)

The API module imports from the package (`.freecad_paths`) and tries FreeCAD GUI operations. It can only work when FreeCAD is installed AND importable from the same Python process — a rare configuration. Most users should use the standalone scripts instead.

### A-008: Example code duplication with core library (RESOLVED)
**Files:** `examples/*/model.py`
**Severity:** Low
**Status:** Fixed in v0.4 (merged into A-001)

All four examples now import `export_model`, `validate_output`, and `generate_report` from the core library. No duplicate export/report functions remain in example files.

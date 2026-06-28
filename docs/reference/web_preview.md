# Web Single-Part Preview — Evaluation

## Status

Phase 4 / Milestone 9 evaluation. This document records the technical assessment of single-part Web preview options. Assembly preview is deferred; assemblies are still viewed and verified in FreeCAD.

## Goal

Display a single CadQuery-generated part in a browser without requiring FreeCAD installation. The viewer is read-only (inspect, rotate, zoom); no browser-side modeling or constraint solving.

## Input formats

CadQuery produces STEP (.step) and STL (.stl). Four conversion paths were evaluated:

### Option A: STL → three.js (STLLoader)

**Path:** `model.stl` → three.js `STLLoader`

- ✅ Zero conversion step; STL files already generated
- ✅ three.js `STLLoader` is built-in and mature
- ✅ Simple static HTML page; no build pipeline
- ⚠️ STL is mesh-only (no color, no assembly tree, no metadata)
- ⚠️ Large file sizes for high-resolution mesh

### Option B: STL → glTF via assimp / trimesh

**Path:** `model.stl` → trimesh → `model.glb`

- ✅ glTF/GLB is compact and web-optimized
- ✅ Supports PBR materials, colors, transparency
- ✅ Broad three.js support via `GLTFLoader`
- ⚠️ Requires `pip install trimesh` (optional dep)
- ⚠️ Adds a conversion step to the pipeline

### Option C: STEP → glTF via FreeCAD headless

**Path:** `model.step` → FreeCAD → `model.glb`

- ✅ STEP is the reference format with full precision
- ✅ FreeCAD can export glTF in headless mode
- ❌ Requires FreeCAD installation (not available on all hosts)
- ❌ This conflicts with the project's design: the CadQuery pipeline must work independently of FreeCAD

### Option D: STEP → three.js via occt-js / web-ifc

- ❌ Experimental and heavy WASM dependencies
- ❌ Not suitable for a lightweight viewer

## Recommendation: Option A + B (STL → three.js STLLoader, optional trimesh → GLB)

**Primary path (Phase 4):** Serve `model.stl` directly to three.js `STLLoader`. Zero additional dependencies.

**Optional enhancement (Phase 5):** Add `trimesh` to `project.optional-dependencies` (`web`) and export `model.glb` alongside `model.stl`. Use three.js `GLTFLoader` for better rendering.

## Viewer architecture

A minimal single-file HTML viewer:

```
web-viewer/
  index.html       — three.js viewer, loads STL/GLB from URL param
  README.md        — usage instructions
```

Features:
- Drag/rotate/zoom with OrbitControls
- Load model via URL query param (`?file=../examples/parts/mounting_plate/model.stl`)
- Wireframe toggle
- Grid plane for scale reference
- No build step, no npm, no framework

## What NOT to do

- **Do not** implement browser-side CAD operations (boolean ops, param editing)
- **Do not** load assemblies in the viewer (use FreeCAD for assembly inspection)
- **Do not** require WebAssembly or heavy build pipelines
- **Do not** add a full web framework or SPA

## Implementation plan (Phase 4 → Phase 5)

1. **Phase 4 (current):** Write `web-viewer/index.html` with STLLoader, document in `docs/web_preview.md`
2. **Phase 4:** Add `export_glb()` to `exporter.py` as optional (requires `trimesh`)
3. **Phase 5:** Add glTF/GLB export to the standard output pipeline
4. **Phase 5:** Enhance viewer with GLB materials support

## Next steps

- [x] Create `web-viewer/index.html` prototype (done, see `web-viewer/index.html`)
- [x] Test with `examples/parts/mounting_plate/model.stl` (done, requires `python -m http.server 8080`)
- [ ] Evaluate `trimesh` STL→GLB conversion quality (Phase 5)

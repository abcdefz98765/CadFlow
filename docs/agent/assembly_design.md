# Assembly 装配

基于 FreeCAD 自动导入多个 STEP 零件并生成装配体。当前主线是：先生成单零件，再运行装配自检，最后交给 FreeCAD 输出 `.FCStd`。

## 端到端示例

当前仓库提供两个装配配置：

- `examples/assemblies/enclosure/assembly.json`：基础装配，使用绝对位置和旋转。
- `examples/assemblies/enclosure/constraint_assembly.json`：约束装配，使用 fixed/coincident 等轻量约束；FreeCAD 布尔干涉默认关闭，只作为可选诊断。

先生成装配需要的零件 STEP：

```bash
python examples/assemblies/enclosure/parts/enclosure_base/model.py
python examples/assemblies/enclosure/parts/enclosure_lid/model.py
python examples/assemblies/enclosure/parts/spacer/model.py
python examples/assemblies/enclosure/parts/wall_bracket/model.py
```

然后运行装配自检：

```bash
python -m ai_native_cad.assembly_validator examples/assemblies/enclosure/assembly.json
```

自检输出：

```text
examples/assemblies/enclosure/assembly_validation.json
examples/assemblies/enclosure/assembly_validation.md
```

只有自检没有 `error` 后，再运行 FreeCAD 装配。

Windows 推荐写法：先配置 `FREECAD_HOME`：

```powershell
$env:FREECAD_HOME="C:\Path\To\FreeCAD"
```

基础装配：

```bash
%FREECAD_HOME%\bin\FreeCADCmd.exe -c "import sys; sys.argv=['scripts/freecad_assembly.py','examples\\assemblies\\enclosure\\assembly.json']; exec(open('scripts/freecad_assembly.py', encoding='utf-8').read())"
```

约束装配：

```bash
%FREECAD_HOME%\bin\FreeCADCmd.exe -c "import sys; sys.argv=['scripts/freecad_constraint_assembly.py','examples\\assemblies\\enclosure\\constraint_assembly.json']; exec(open('scripts/freecad_constraint_assembly.py', encoding='utf-8').read())"
```

Linux/macOS 若 `freecadcmd` 在 PATH：

```bash
python -m ai_native_cad.assembly_validator examples/assemblies/enclosure/assembly.json
freecadcmd scripts/freecad_assembly.py examples/assemblies/enclosure/assembly.json
freecadcmd scripts/freecad_constraint_assembly.py examples/assemblies/enclosure/constraint_assembly.json
```

## 装配自检

装配自检是 Agent 修复装配的第一依据，它不依赖 FreeCAD 布尔求交，优先检查稳定、可解释的工程事实：

- 每个 `parts[].step` 是否存在。
- 每个零件是否有对应 `report.json`。
- 单零件报告是否有效。
- 单零件是否是 single solid。
- 非锚点零件是否有接触/支撑关系。
- `required_contacts` 中声明的装配接触是否成立。
- bbox 重叠是否需要复核，或是否已通过 `allowed_bbox_overlaps` 说明为外壳空腔/安装贴合。
- 允许重叠、允许小间隙和必需接触是否写清楚 `reason` / `intent`。

装配配置中的 `validation` 字段用于表达装配意图：

```json
{
  "validation": {
    "anchors": ["enclosure_base"],
    "contact_tolerance": 0.15,
    "min_clearance": 0.5,
    "allowed_bbox_overlaps": [
      {
        "part1": "enclosure_base",
        "part2": "spacer_*",
        "reason": "spacers sit inside the enclosure cavity and on top of bosses"
      }
    ],
    "allowed_close_clearances": [
      {
        "part1": "enclosure_base",
        "part2": "enclosure_lid",
        "reason": "nominal 0.5mm clearance can report slightly lower after STEP/bbox tolerance"
      }
    ],
    "required_contacts": [
      {
        "part1": "enclosure_lid",
        "part2": "spacer_a",
        "axis": "z",
        "intent": "lid is supported by spacer_a"
      }
    ]
  }
}
```

`required_contacts` 应包含 `intent`；`allowed_bbox_overlaps` 和 `allowed_close_clearances` 应包含 `reason`。这些字段用于约束 Agent 的修复行为：只有真实设计意图才能成为例外，不能用宽泛例外掩盖干涉。

报告分级：

- `error`：必须先修复，例如缺 STEP/report、多实体零件、悬空零件、必需接触失败。
- `warning`：需要复核，例如 bbox 可能重叠、间隙小于阈值、旋转未参与 bbox 自检。
- `possible_interferences`：bbox 级可疑干涉，不等同于真实实体干涉，尤其是外壳空腔场景。

## 输出

```text
examples/assemblies/<assembly>/
  ├─ <name>.FCStd                 # FreeCAD 装配文件
  ├─ bom.csv                      # 物料清单
  ├─ assembly_report.json         # FreeCAD 装配报告
  ├─ assembly_validation.json     # 装配自检报告
  └─ assembly_validation.md       # 可读自检报告
```

## 约束装配

`scripts/freecad_constraint_assembly.py` 支持：

| 类型 | 说明 | 参数 |
|------|------|------|
| `fixed` | 固定零件到绝对位置 | `position`, `rotation` |
| `coincident` | 将 part1 底面对齐到 part2 顶面并居中 | `part1`, `part2`, `offset` |
| `concentric` | 将两个零件的质心在 XY 平面对齐 | `part1`, `part2` |
| `parallel` | 沿指定轴设置平行偏移 | `part1`, `part2`, `axis`, `offset` |
| `distance` | 沿指定轴设置两零件质心间距 | `part1`, `part2`, `axis`, `distance` |

这些约束是轻量定位规则，不等同于 FreeCAD Assembly4 或商业 CAD 的完整约束求解器。Agent 应优先通过 `assembly_validator` 修复基本装配错误，再运行 FreeCAD 输出。

### 干涉检查

`scripts/freecad_constraint_assembly.py` 仍支持 `"check_interference": true`，但默认不建议开启。FreeCAD `Shape.common()` 对 STEP 导入体、共面接触、小间隙和外壳空腔可能出现误报或漏报。

推荐顺序：

1. 先跑 `python -m ai_native_cad.assembly_validator examples/assemblies/enclosure/assembly.json`。
2. 修复所有自检 `error`。
3. 用 FreeCAD 打开 `.FCStd` 人工复核。
4. 仅在需要几何诊断时开启 `check_interference`。

## 打开装配结果

基础装配完成后打开：

```text
examples/assemblies/enclosure/enclosure_assembly.FCStd
```

约束装配完成后打开：

```text
examples/assemblies/enclosure/constraint_assembly/enclosure_constraint_assembly.FCStd
```

在 FreeCAD 中选择 `File -> Open`，打开上面的 `.FCStd` 文件。打开后可在模型树中看到 `enclosure_base`、`enclosure_lid`、`spacer_*` 和 `wall_bracket_*` 装配零件。

若 FreeCAD 打开后视图区空白：

1. 先看左侧模型树是否有装配对象。
2. 如果有对象，选中根文档或所有对象，然后点击 `Fit all` / `Zoom to fit`。
3. 如果对象图标是灰色或隐藏状态，选中对象后按空格键切换可见性。
4. 如果仍然看不到，切到 `View -> Standard views -> Isometric` 后再执行 `Fit all`。

## 限制

- 基础脚本 `scripts/freecad_assembly.py` 仅支持绝对位置、XYZ 旋转、FCStd 保存和 BOM 导出。
- 约束脚本 `scripts/freecad_constraint_assembly.py` 支持 fixed、coincident、concentric、parallel、distance 和可选干涉检查。
- 当前约束是基于包围盒和质心的轻量实现，不等同于完整 FreeCAD Assembly4/商业 CAD 约束求解器。
- 自检以装配意图和 bbox 数学检查为主，不能替代人工工程复核。
- 需要 FreeCAD 1.0+ 本地安装。

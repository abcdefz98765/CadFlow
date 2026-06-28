# FreeCAD Handoff

从 CadQuery 输出的 STEP 文件过渡到 FreeCAD 工程环境。

## 前提条件

- FreeCAD 1.0+ 已安装（https://www.freecad.org）
- CadQuery 已生成 `model.step`

## 使用方式

### 方法一：独立脚本（推荐）

用 FreeCAD 自带的 Python 运行：

```bash
# Windows (adjust path to your FreeCAD installation)
"C:\Program Files\FreeCAD 1.0\bin\freecadcmd.exe" scripts/freecad_handoff.py examples/parts/mounting_plate/model.step examples/parts/mounting_plate
```

```bash
# Linux
freecadcmd scripts/freecad_handoff.py examples/parts/mounting_plate/model.step examples/parts/mounting_plate
```

### 方法二：Python 模块

将 FreeCAD 的 bin/lib 目录添加到 PYTHONPATH 后使用：

```python
from pathlib import Path
from ai_native_cad.freecad_handoff import run_handoff

result = run_handoff(
    step_path="examples/parts/mounting_plate/model.step",
    output_dir="examples/parts/mounting_plate",
)
print(result)
```

## 输出

每次 handoff 生成：

```
examples/parts/<part>/
  ├─ <part>.FCStd          # FreeCAD 原生文件
  ├─ freecad_preview.png   # 基础截图（需 GUI 模式）
  ├─ freecad_report.json   # Handoff 报告
  └─ model_freecad.stl     # FreeCAD 导出的 STL
```

## 报告内容

`freecad_report.json` 包含：

- STEP 导入状态
- FCStd 保存路径
- 几何信息：包围盒、体积、面积、实体/面/边数量
- 错误和警告信息

## 手动验证步骤

1. 打开 FreeCAD
2. `File → Open` → 选择 example 目录下生成的 `<part>.FCStd`
3. 检查模型几何是否正确
4. 可选：切换到 TechDraw 工作台创建工程图

## 限制

- v0.1 不自动生成工程图（将在 v0.2 支持）
- 截图仅在 GUI 模式下可用
- 需要 FreeCAD 本地安装

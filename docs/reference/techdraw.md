# TechDraw 工程图

基于 FreeCAD TechDraw 工作台自动生成三视图和 PDF 工程图。

## 使用方式

```bash
freecadcmd.exe scripts/freecad_techdraw.py examples/parts/mounting_plate/model.step examples/parts/mounting_plate
```

## 输出

```
examples/parts/<part>/
  ├─ <part>_drawing.pdf       # PDF 工程图
  ├─ <part>_drawing.svg       # SVG 矢量图
  ├─ <part>_techdraw.FCStd    # 含图纸的 FreeCAD 文件
  └─ techdraw_report.json     # 生成报告
```

## 图纸内容

| 视图 | 说明 |
|------|------|
| Front（前视图） | XY 平面投影 |
| Top（俯视图） | 从上向下看 |
| Right（右视图） | 从右侧看 |
| Isometric（等轴测） | 3D 视角 |

## 尺寸标注

- v0.2 尝试添加包围盒尺寸
- 自动标注不承诺完整
- 可在 FreeCAD 中手动补充标注

## 限制

- 需要 FreeCAD 1.0+ 本地安装
- 尺寸标注为辅助性，不保证工业标准完整性
- 复杂曲面零件可能需要手动调整视图

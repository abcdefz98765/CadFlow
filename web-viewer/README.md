# Web STL 查看器

轻量级 three.js 单零件 STL 预览器，无需 FreeCAD 安装。

## 使用方式

### 方式一：拖放加载

直接用浏览器打开 `web-viewer/index.html`，将任意 STL 文件拖放到浏览器窗口即可查看。

### 方式二：URL 参数加载

先启动本地 HTTP 服务器（因为 `file://` 协议下浏览器会阻止加载相对路径的 STL 文件），再通过 `?file=` 参数指定 STL 路径：

```bash
# 在项目根目录启动 HTTP 服务器
python -m http.server 8080

# 浏览器访问
# http://localhost:8080/web-viewer/index.html?file=../outputs/enclosure_lid/model.stl
```

### 方式三：命令行一键启动

Windows:

```powershell
start python -m http.server 8080 && start http://localhost:8080/web-viewer/index.html?file=../outputs/enclosure_lid/model.stl
```

Linux/macOS:

```bash
python -m http.server 8080 &
open http://localhost:8080/web-viewer/index.html?file=../outputs/enclosure_lid/model.stl
```

## 快捷键

| 按键 | 功能 |
|------|------|
| `W` | 切换线框模式 |
| `G` | 切换参考网格 |
| `R` | 重置视角 |

## 鼠标操作

| 操作 | 说明 |
|------|------|
| 左键拖拽 | 旋转 |
| 右键拖拽 / Shift+左键 | 平移 |
| 滚轮 / 双指缩放 | 缩放 |

## 技术说明

- 基于 three.js 0.160，通过 CDN 加载（需联网）
- 仅支持 STL 格式，显示单一零件
- CAD 坐标系（Z-up）自动转换为浏览器坐标系（Y-up）
- 不替代 FreeCAD 装配，不做浏览器内建模或约束求解

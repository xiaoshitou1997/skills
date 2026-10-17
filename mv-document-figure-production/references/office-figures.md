# Word 与 PowerPoint 配图

适用于在 DOCX/PPTX 正文制作途中插入图片，或给已有文档准确换图。图源与渲染见 [渲染指南](rendering.md)；本指南只处理 Office 配图，不负责全文与整套幻灯片的写作和排版。

## 使用前

先生成目标格式的文档和 PNG。新建文档可以由相应文档制作能力、用户已有模板或项目工具完成，再在同一任务里将 PNG 插入该新文件。脚本使用 Python 3 标准库读取 Office 文件，不要求安装 `python-docx` 或 `python-pptx` 才能插入图；它不负责从空白生成整篇正文或幻灯片。

`SKILL_ROOT` 需显式赋值为本次加载的 skill 安装目录，并保持当前工作目录为用户文档项目。以下示例中的输入与输出路径必须不同，且输出路径不得已存在；检查成品后再决定是否将旧文件归档或替换。需要多个图时，每次以前一次输出为下一次输入，最终只交付验证过的文件。

```bash
SKILL_ROOT="/实际绝对路径/mv-document-figure-production"
python3 "$SKILL_ROOT/scripts/office_figures.py" --help
```

## Word：列出、插入、替换

插入前在文档中放一段仅用于定位的唯一文字，例如 `[[FIGURE:login-sequence]]`；该段落必须在图应出现的位置**之前**。脚本在该段落后插入单独的图片段落，保留原锚点段落供文档编写者后续编辑，选定的宽度用英寸表示，高度按 PNG 比例计算。

```bash
python3 "$SKILL_ROOT/scripts/office_figures.py" docx insert draft.docx illustrated.docx --after '[[FIGURE:login-sequence]]' --png fig-out/login-sequence.png --width 5.8
```

已有图先列出图片的 drawing ID 和相邻文本，人工核对目标，再按唯一 ID 替换；没有 ID 时可用 `--caption`，其值必须完整出现在目标图相邻的一个段落中且全文档唯一，匹配多处时脚本拒绝执行。替换保持原显示宽度，以 PNG 的实际比例计算高度；如果绘图对象与锚定、裁切、外部链接或兼容性标记混用且脚本不能安全处理，应停止并改用原文档制作工具。

```bash
python3 "$SKILL_ROOT/scripts/office_figures.py" docx list draft.docx
python3 "$SKILL_ROOT/scripts/office_figures.py" docx replace draft.docx revised.docx --drawing-id 12 --png fig-out/login-sequence.png
```

## PowerPoint：列出、插入、替换

先列出幻灯片序号与图形 ID/名称。插入时明确页码（从 1 开始）及目标区域，坐标、宽高单位是英寸；图片按比例置于区域中央。文档制作流程负责选择版式、预留插图区域及图注。生成幻灯片之后应立即插图，而不是让用户在 PPT 中手工粘贴。

```bash
python3 "$SKILL_ROOT/scripts/office_figures.py" pptx list draft.pptx
python3 "$SKILL_ROOT/scripts/office_figures.py" pptx insert draft.pptx illustrated.pptx --slide 2 --png fig-out/architecture.png --left 1.0 --top 1.5 --width 11.0 --height 5.0 --name architecture
```

替换现有图片时只用指定幻灯片上的图形 ID 或唯一名称；保持其区域与中心点，新图片按比例置于原区域内。若目标图有裁切、旋转或与其他图形组合导致结果不确定，停止自动替换并使用文档制作工具检查与修复。

```bash
python3 "$SKILL_ROOT/scripts/office_figures.py" pptx replace draft.pptx revised.pptx --slide 2 --shape-id 8 --png fig-out/architecture.png
```

## 核验与边界

脚本在写入前检查选择是否唯一、PNG 与 Office 包是否有效，并在写入后检查 ZIP 完整性与新图片引用。完成后打开 Word/PPT 或用现有本地渲染能力预览实际页面，确认页面换行、版心、图注、宽高比、文字可辨识和背景；没有打开目标应用时注明只完成结构验证。不同绘图类型、图像裁切、母版占位符以及复杂兼容层应使用对应的文档制作能力，不能靠猜测包内媒体文件名处理。本文只负责图片操作，工程文档内容见 mv-engineering-doc-writer。

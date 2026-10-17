# 图源与本地渲染

适用于为文档制图、截图并生成可插入图片的阶段。用户要求的格式和项目现有制图约定优先；本文不决定文档正文内容。

## 图源与出口

| 用途 | 可编辑来源 | 文档内形式 |
| --- | --- | --- |
| 时序、状态、ER、类图 | Mermaid `.mmd`；需要特定 UML 语法时选 PlantUML | Markdown 中可用 Mermaid 块，Word/PPT 用本地 PNG |
| 架构、拓扑、页面、需要控制布局的流程图 | HTML/CSS 与内联 SVG；简单流程也可用 Mermaid | PNG，必要时附原 HTML |
| 已有系统页面 | 目标页面 URL、环境、状态与截图时间 | 本地截图 PNG，且记录来源 |

文本图源保存在文档项目的 `fig-src/`，图像保存在 `fig-out/`。保持命名对应，例如 `fig-src/login-sequence.mmd` → `fig-out/login-sequence.png`；文档有多个版本时使图片和源文件随版本一起更新。源文件允许必要的样式：格式与主题要求由用户和目标文档决定，不把某种工具的默认主题当作全部文档的统一规范。

## Mermaid

1. 检查项目现成的 Mermaid CLI（`mmdc` 或项目已安装的 `@mermaid-js/mermaid-cli`）、浏览器及字体；尚未安装时说明依赖，经用户项目的包管理器按既定锁文件安装，不使用会隐式联网安装的 `npx mmdc`。
2. 在文档项目目录调用已安装的 CLI，使用绝对输入/输出路径和适合版心的宽度。示例：

   ```bash
   ./node_modules/.bin/mmdc -i fig-src/login-sequence.mmd -o fig-out/login-sequence.png -b white -t default -w 1600 -s 2
   ```

3. 浏览器位置由渲染器或项目配置发现；在需要 Puppeteer 配置的环境中，将实际可用的 Chrome/Chromium 路径写入**项目临时配置**并通过 `-p` 指向它。Windows 可检查 Chrome/Edge 安装位置，macOS/Linux 可用系统路径或 `command -v`。不要把一台机器的路径写入共享 skill，不默认关闭浏览器沙箱。
4. Mermaid、PlantUML、Graphviz、D2 各有独立依赖；只有在本机能运行且输出可检查时才选择。缺工具时保留可编辑源并明确图像尚未生成，不声称 Office 配图已完成。

## HTML/SVG 和现有页面

HTML 图源使用明确的画布与字体，边缘留出安全距。浏览器无头截图可用于静态 HTML；页面含 JS、动态字体或长图时等待内容稳定并按内容尺寸核对截图。优先使用已配置的本地浏览器/截图能力；命令行 Chrome 路径通过实际安装发现，不写死盘符。页面截图只访问用户允许的环境，不因制图请求擅自启动生产服务或上传内容。

## 交付检查

检查 PNG 是否可打开、文字是否清晰、背景对比是否满足目标文档、整体未裁切且宽高比正常。插入 Word/PPT 后再次检查实际版心或幻灯片上的尺寸与图注；单独检查图片不能代替目标文档检查。本文只负责渲染阶段，文件插入与替换参见 [Office 配图指南](office-figures.md)。

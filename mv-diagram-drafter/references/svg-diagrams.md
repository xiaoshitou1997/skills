# SVG 图源画法与渲染

适用于精确布局图源（组网图、机架连线图、架构图、页面示意）的 HTML/SVG 画法、结构类图的 Mermaid 适用边界与本地渲染。用户对格式、尺寸与主题的要求优先；本文不涉及插图进文档，插入与替换见 mv-doc-figure-placement。

## HTML/SVG 图源规范

- 单文件自包含：样式写 `<style>`，不引用外网 CSS、JS、字体、图标库；字体用系统安全字体栈（如 `system-ui, "Microsoft YaHei", sans-serif`）。
- 画布明确：`body` 固定宽高即画布尺寸，四周留白不小于 24px；`<svg>` 的 `viewBox` 与画布一致，渲染窗口尺寸按画布设定。
- 布局由算法产生：整图布局写 layout_gen spec 生成（下节）；生成器未覆盖的局部才手调坐标，手调遵守同一网格与间距；同类图元同形状同尺寸，间距均匀（建议不小于 32px）。
- 网络设备符号自绘简单几何图形，路由器、交换机、防火墙、服务器各一种固定画法，全图一致并与图例对应；不从外部图标库取图。
- 连线用 `<line>`/`<path>` 直角折线，箭头用 `<marker>` 定义；线不穿过节点与文字，转折对齐图元边缘；标注放线段中段并避开交点。
- 文本防溢出：节点宽度按最长文本预留或换行；节点名为主文本，型号/IP 等以小一号辅文本在第二行呈现。
- 标题置顶，图例置于画布角落空白处，不与图元重叠。

## layout_gen 布局生成器

精确摆放图的坐标不由人手摆：spec（JSON）进，自包含 HTML 出，同 spec 必同输出。生成器内置规则：坐标取 4px 网格，节点默认 168×64，行距=行内间距=64，每行居中，正交走线（直落/L/同源总线/双机交叉双通道/同排直连与绕行），分区框=成员包围盒外扩，节点文字超宽断言失败。

```bash
python3 "${SKILL_ROOT}/scripts/layout_gen.py" spec.json "fig-src/<图名>.html"
python3 "${SKILL_ROOT}/scripts/layout_gen.py" --help   # 两种 spec 模板与字段
```

- 分层/组网模板：`rows`（样式、band 底板、节点）+ 可选 `zones`（成员用 align 对齐到某节点同列）+ `links`（straight/L/cross/dashh，可带 label）；band 行画分层/安全域底板并带 label，`"legend": false` 关闭图例。
- 表达层通道（编码职责见[图面语法](visual-grammar.md)）：节点 `shape` ∈ box|db|cloud（方框=组件、圆柱=存储、云=外部网络）、`ghost: true` 虚框半透明=逻辑存在/未激活；行 `role` 覆盖该行样式在图例里的名称（默认用内置网络语义名）；节点 `style` 引用内置六样式或顶层 `"styles": {"名": [填充色, 边线色, 图例名]}` 的声明（机制同 link-tones，重名内置即失败，未声明即失败）；链路 `tone` 引用顶层 `"link-tones"` 声明（通道名→green|blue|purple|orange，线色=承载通道），引用未声明的通道名直接失败；`"line-legend": {"solid": ..., "dash": ...}` 覆盖实/虚线图例文案。图例按实际用量生成，未动用的通道不进图例；一图一色一义，复用内置色前先确认语义不撞。
- 容器嵌套与双站点镜像：zone 或站点域成员可以是 `{"kind": "group", "name": ..., "members": [...]}` 递归容器（限 3 层，标题超宽断言；含 group 的 zone 不支持 align，成员左→右排布）；多站点容灾用顶层 `"region"`：`sites[0]` 完整声明 `domains`（域结构同 zone），`sites[1]` 只写 `name`/`role`/`style`/`ghost`，引擎深拷贝派生镜像站点（叶子 id 加 `-b` 后缀，`style` 整站覆盖、`ghost: true` 整站虚框=备用/未激活）；对称链路只写一份——`from`/`to` 都不带 `-b` 的链路自动派生镜像链路（标注随链继承；rows 节点无镜像则该端保持），跨站链路不派生，`"mirror": false` 显式关闭，派生结果与手写重复（会画双线）即失败；`region` 与 `zones` 互斥，`rows` 仍必备。
- 时序模板：`"template": "sequence"` + `lanes` + `messages`（from==to 为自消息，dash 为返回/异步）；本机有 `mmdc` 时时序图仍按 Mermaid 出图源，无 `mmdc` 时用本模板渲染，交付说明注明用了哪种。
- 断言失败（文字超宽、直落不在目标框内、扇入放不下）按报错回改 spec 重跑，不绕过断言、不手改产物坐标。
- 走线判定：跨行目标走直落/L/总线/交叉（上行链路同规则，折线向上）；同一行目标自动改走面向边直连，被中间节点挡住时走行下方绕行通道（容器内节点把下缘抬到双方非共有容器之外，跨站链路落在大区框内侧）。

## Mermaid 适用边界

时序图、状态图、ER 图、类图优先 Mermaid，需要特定 UML 语法时选 PlantUML；结构简单的流程图与单层调用关系也可用 Mermaid；组网图、机架连线图与需要精确摆放的图不用自动布局，走 layout_gen（上节）。渲染使用项目已安装的 mermaid CLI（`mmdc`），显式设置宽度与倍率；未安装时说明依赖并经项目包管理器按既定锁文件安装，不使用隐式联网安装的 `npx mmdc`；缺工具时保留图源并如实注明未渲染（时序图可改用 layout_gen 的 sequence 模板渲染）。状态、ER 等带环路的图无自动布局引擎时不手摆坐标，保留图源注明未渲染。

## 本地渲染与核验

1. 优先使用当前会话已配置的浏览器预览/截图能力打开图源并截图。
2. 无该能力时用本 skill 脚本发现本机 Chrome/Edge 无头渲染（`SKILL_ROOT` 赋值见 SKILL.md）：

   ```bash
   bash "$SKILL_ROOT/scripts/render_diagram.sh" fig-src/campus-a.html fig-out/campus-a.png --width 1600 --height 1000 --scale 2
   ```

   `--width`/`--height` 必须与图源画布一致；`--scale` 为成图倍率。
3. 成图核验：打开 PNG 核对文字清晰、四周无裁切、宽高比与画布一致、分区底色与文字对比可读；核验不过回到图源修改后重渲染，不直接修改成品图。
4. 交付成图记录渲染方式（预览截图或脚本、倍率）与核验结果；未渲染时如实注明。

## 边界

本文只管图源与成图；图进文档后的插入、替换与文档内核验归 mv-doc-figure-placement，其文档侧嵌入判定以该 skill 的渲染指南为准。

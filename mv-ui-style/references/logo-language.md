# 家族 logo 语言

本文定义 mv-ui-style 家族 logo 的构造规则、变体、使用规范与逐应用定档流程：全家族一套 logo 形制语言，各应用的图形标记（mark）在同一语言下定档，与 tokens 同为家族视觉资产——logo 取形取色均出自家族 tokens 条款，不另立体系。tokens 落盘形态见 [design-tokens.md](design-tokens.md)，取色推导见 [color-derivation.md](color-derivation.md)，原创性判定基线见 [originality-rules.md](originality-rules.md)；与 SKILL.md 冲突时以 SKILL.md 为准。

## 语言固定项（全家族一套）

家族参数一次性定档，逐应用定档 mark 时不重议：

| 项 | 家族值 | 依据 |
| --- | --- | --- |
| 构造栅格 | 24px 基准栅格，导出尺寸取 16/24/32/48/64/128/256/512 | 与家族图标 24px 栅格同源，整数倍缩放形制不重排 |
| 几何语言 | 圆角取家族圆润档方向（连续大圆角），半径在 24 栅格内取整格；线条形笔画宽 1.5px、圆头端点；面形笔画外轮廓圆角化 | 与家族圆角圆润档、图标形制条款同一语言，mark 与界面图标同族 |
| 用色 | mark 主体单色：亮色取 accent 主档、暗色取暗色 accent 档、随文字场景取 `currentColor`；辅助形从中性阶取色；不用语义色，不引入 tokens 外颜色 | 单色 mark 全场景可用且过得了对比度校验，每个用色可追溯 tokens |
| 字标 | wordmark 用 OFL 授权字体按家族字重 500/700 排版，交付一律转路径；系统栈字体不进 wordmark 交付物 | 系统字体许可不覆盖标识用途；转路径后不分发字体软件，授权干净 |
| 渐变 | 主形不用渐变；确需渐变时两端点必须是家族推导色并记入定档记录 | 渐变破坏单色复用与可校验性 |
| 容器形 | 应用图标容器形状按目标平台规范（macOS、Windows、favicon 各随其规），mark 内容按本语言构造 | 平台形状是平台规范不是家族资产 |

## 变体与使用规范

每个应用 mark 定档时产出齐套变体：

- **基准形**：单色 mark SVG，主体随文字色（`currentColor`），全场景通用。
- **彩色形**：基准形换 accent 主档；暗色场景换暗色 accent 档。
- **组合形**：mark 与 wordmark 横排，间距按 clear space。
- **图标形**：16px 下可辨识的最简形，作 favicon 与最小场景。

clear space：mark 四周留白 ≥ mark 高度的 25%，组合形中 mark 与 wordmark 间距同值。最小尺寸：mark 16px、wordmark 12px（家族字号档最小档）；低于最小尺寸改用更简变体，不用缩小尺寸迁就。

mark 用色逐对跑对比度校验，部件级门槛 3.0（与焦点环、on-accent 同标）：

```bash
SKILL_ROOT="/实际绝对路径/mv-ui-style"
python3 "${SKILL_ROOT}/scripts/check_contrast.py" --min 3 <mark 色> <应用底色>
```

校验不过按 [color-derivation.md](color-derivation.md) 的回改思路收 L/C 重推，不降阈值、不删检查项迁就。

## 逐应用定档流程

1. 从应用名与职责取题材：首字母形、职责符号的构造化处理等几何抽象，题材与构造参数可追溯。
2. 按语言固定项产出 2–3 个 SVG 候选，逐个过 [originality-rules.md](originality-rules.md) 照抄判定三问，另过本参考「商标域加严判定」。
3. 用户定档选定候选；SVG 落 master `~/.mv/ui-style/logo/<app>.svg`（环境变量 `MV_UI_STYLE_HOME` 覆盖，供测试与隔离），SVG 头注释记题材来源、构造参数、定档日期与授权声明，格式对齐 master tokens 头注释惯例。
4. 应用项目内放副本并在头部注明 master 来源与同步日期；界面内使用取副本或构建引入，不改形不换色，换色仅限家族 tokens 色值。

家族级共用徽标非必需；需要时按同一流程定档，落 `~/.mv/ui-style/logo/logo.svg`。

## 商标域加严判定

logo 是家族视觉资产中商标属性最强的一类，在照抄判定三问之上加两条：

- **近似混淆测试**：与所参照过或同题材的现有产品 logo 并排，普通用户能否混淆或指认近似？能即回炉重推——三问的「不可指认同源」在 logo 上收紧为「不可近似混淆」。
- **不取现成图形充当**：图标库图形、素材站图形不直接充当 mark——授权许可的是使用，不授予独占性，同款图形他人同样可用而 mark 须独占；mark 一律按语言固定项自绘。

## 自查记录格式

交付说明按三问与加严条各记一句结论，例：「并排测试：与 Xshell、Tabby 标记并排不可近似混淆；来源追溯：题材=应用职责符号构造化，构造参数见 SVG 头注释；授权凭证：自绘 SVG 权利自持，wordmark 为 OFL 字体转路径。」

边界：本参考管家族 logo 的形制、变体、使用与定档流程；插画与营销素材不在范围，各平台应用市场的图标审核规范不在范围。

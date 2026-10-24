# 设计 tokens 与模板

本文是 mv-ui-style 家族 tokens 的标准落盘形态：命名约定、CSS variables 模板与 Tailwind 4 映射。取值推导过程见 [color-derivation.md](color-derivation.md)，原创性判定见 [originality-rules.md](originality-rules.md)；与 SKILL.md 冲突时以 SKILL.md 为准。

## 命名约定

前缀 `--ui-`，结构 `--ui-<类别>-<名称>`，类别：`space` / `text` / `leading` / `weight` / `radius` / `duration` / `ease` / `color`。家族固定项与推导项同一命名空间；推导值不另起 `--brand-*`、`--theme-*` 一类并行体系，一个应用只保留一套 tokens。

## CSS variables 模板

```css
/* mv-ui-style 家族 tokens
   家族参数: hue=264 · 色阶骨架 C0.13 · accent 主档 L0.58/C0.2294 · 圆角=圆润 8/14/20 · 动效=140/240/400ms cubic-bezier(0.32,0.72,0,1) · 材质=毛玻璃 · 密度=标准（2026-10-23 苹果风定档；2026-10-24 accent 复刻修订）
   定档记录: 2026-10-23 苹果风全参数定档；2026-10-24 accent 复刻修订（accent L0.58/C0.2294＝用户原工具蓝 #2F6BFF 逐位复刻，按钮白字门槛 3.0 部件级）
   偏离记录: <无；或逐条：偏离家族哪一条、理由> */
:root {
  /* —— 家族固定项 —— */
  --ui-space-1: 4px;  --ui-space-2: 8px;  --ui-space-3: 12px;
  --ui-space-4: 16px; --ui-space-6: 24px; --ui-space-8: 32px;
  --ui-space-12: 48px;
  --ui-text-xs: 12px; --ui-text-sm: 14px; --ui-text-md: 16px;
  --ui-text-lg: 20px; --ui-text-xl: 24px; --ui-text-2xl: 30px;
  --ui-leading-body: 1.6;
  --ui-leading-title: 1.3;
  --ui-weight-regular: 400;
  --ui-weight-medium: 500;
  --ui-weight-bold: 700;
  --ui-font: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;
  --ui-duration-fast: 140ms;   /* 微交互：悬停、按压反馈 */
  --ui-duration-normal: 240ms; /* 常规过渡：展开、切换 */
  --ui-duration-slow: 400ms;   /* 面板与页面级 */
  --ui-ease: cubic-bezier(0.32, 0.72, 0, 1); /* 苹果风转场曲线（2026-10-23 定档） */
  /* 圆角三档，2026-10-23 苹果风定档圆润：8/14/20（备选标准 4/8/16、锐利 2/4/8） */
  --ui-radius-sm: 8px;  /* 输入框、标签 */
  --ui-radius-md: 14px; /* 按钮、卡片 */
  --ui-radius-lg: 20px; /* 弹窗、面板 */
  /* —— 推导项：按 color-derivation.md 步骤从种子参数生成 —— */
  --ui-hue: 264;      /* 种子：家族主色色相（2026-10-24 复刻修订定档） */
  --ui-seed-c: 0.13;  /* 种子：色阶骨架 C（2026-10-23 定档标准 0.13）；灰调/深调为修订候选，取值见 color-derivation */
  --ui-accent-c: 0.2294; /* accent 主档 C：复刻用户原工具蓝 #2F6BFF（2026-10-24 定档，原值反推 0.2289 取整）；灰调 0.07–0.10 / 深调 0.08–0.12 */
  --ui-color-accent: oklch(0.58 var(--ui-accent-c) var(--ui-hue));
  --ui-color-accent-strong: oklch(0.44 0.12 var(--ui-hue)); /* C 定档字面，与 master 一致 */
  --ui-color-accent-soft: oklch(0.95 0.024 var(--ui-hue)); /* C 定档字面，与 master 一致 */
  --ui-color-on-accent: <校验通过的白或近白，部件级门槛 ≥3.0；正文小字与链接文字改用 accent-strong 过 4.5>;
  --ui-color-bg: oklch(0.985 0.004 var(--ui-hue));
  --ui-color-surface: oklch(1 0 var(--ui-hue));
  --ui-color-border: oklch(0.9 0.006 var(--ui-hue));
  --ui-color-text: oklch(0.25 0.01 var(--ui-hue));
  --ui-color-text-muted: oklch(0.42 0.015 var(--ui-hue));
  --ui-color-success: oklch(0.55 0.12 145);
  --ui-color-warning: oklch(0.65 0.13 85);
  --ui-color-danger: oklch(0.55 0.16 27);
  --ui-color-info: oklch(0.58 0.11 var(--ui-hue));
  /* 焦点环：2px + 2px 外扩，颜色取 accent，对底 ≥3:1 校验 */
  --ui-focus-ring-width: 2px;
  --ui-focus-ring-offset: 2px;
  --ui-focus-ring-color: var(--ui-color-accent);
  /* 毛玻璃材质（苹果风）：仅用于头部/侧栏等覆盖层，正文面板不用 */
  --ui-material-blur: saturate(180%) blur(20px);
  --ui-material-surface: oklch(1 0 var(--ui-hue) / 0.72);
}

/* 暗色：同一 hue 推导，映射规则见 color-derivation.md，不另行配色 */
[data-theme="dark"] {
  --ui-color-bg: oklch(0.17 0.008 var(--ui-hue));
  --ui-color-surface: oklch(0.22 0.01 var(--ui-hue));
  --ui-color-border: oklch(0.32 0.012 var(--ui-hue));
  --ui-color-text: oklch(0.93 0.006 var(--ui-hue));
  --ui-color-text-muted: oklch(0.72 0.012 var(--ui-hue));
  --ui-color-accent: oklch(0.76 0.125 var(--ui-hue)); /* C 定档字面，与 master 一致 */
  --ui-color-accent-strong: oklch(0.85 0.075 var(--ui-hue)); /* C 定档字面，与 master 一致 */
  --ui-color-accent-soft: oklch(0.28 0.06 var(--ui-hue)); /* C 定档字面，与 master 一致 */
  --ui-color-on-accent: <校验通过的深或近黑>;
  --ui-color-success: oklch(0.72 0.12 145);
  --ui-color-warning: oklch(0.78 0.12 85);
  --ui-color-danger: oklch(0.68 0.15 27);
  --ui-color-info: oklch(0.75 0.1 var(--ui-hue));
  --ui-material-surface: oklch(0.22 0.01 var(--ui-hue) / 0.72);
}
```

`--ui-hue`、`--ui-seed-c` 与 `--ui-accent-c` 是三个种子参数：主色 hue（2026-10-24 复刻修订定档 264）、色阶骨架 C（2026-10-23 定档标准 0.13，管 10 档全谱色阶的彩度基带）、accent 主档 C（2026-10-24 accent 复刻修订定档 0.2294＝用户原工具蓝 #2F6BFF，管强调三档与暗色强调组；亮端色阶已被 sRGB 色域上限钉住，accent 提彩度不牵动色阶，故独立成参）。三个参数在 `:root` 内声明一次，全部推导色引用它们——修订家族风格只改这几处，改完同步各应用副本。master 文件（`~/.mv/ui-style/tokens.css`）头部注释记家族参数与定档记录，应用副本头部注释改记 master 来源与同步日期，两者都不省略偏离记录。跟随系统的明暗切换在应用入口按 `prefers-color-scheme` 设 `data-theme`，不在 tokens 内做双份取值。

## Tailwind 4 映射

```css
@theme inline {
  --color-accent: var(--ui-color-accent);
  --color-accent-strong: var(--ui-color-accent-strong);
  --color-bg: var(--ui-color-bg);
  --color-surface: var(--ui-color-surface);
  --color-content: var(--ui-color-text);
  --color-muted: var(--ui-color-text-muted);
  --radius-card: var(--ui-radius-md);
  --spacing: 4px; /* Tailwind 4 间距倍数基准，与 4px 栅格同源 */
}
```

其他技术栈（Electron 直接引入 tokens.css、组件库主题变量、移动端主题文件）按同一命名做一层映射，映射关系写在 tokens 文件尾注释；不把家族值复制散落到组件样式里。

边界：本模板管家族 tokens 的落盘形态；应用内组件样式组织与 CSS 架构不在本参考范围。

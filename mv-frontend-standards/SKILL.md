---
name: mv-frontend-standards
description: 编写、修改、重构或审查前端代码时使用（React、TypeScript 及其他前端框架；含 shadcn-admin 后台管理类项目与 Taro H5/小程序端），覆盖组件分层、TypeScript 类型契约、数据获取与服务层、状态管理、路由、错误与国际化文案、构建环境变量、前端安全、页面交互体验基线、可访问性与性能预算；框架与脚手架专属条款按项目实际栈应用。技术栈选型与版本基线归 mv-tech-stack-baseline。
---

# 前端规范

## 作用与优先级

这是**规范型 Skill**，在 Agent 编码、审查、测试期间引用；不负责流程编排，不负责构建出包、镜像与启动调试。适用于前端项目：通用条款对任意前端框架适用，React/Vite 与 shadcn-admin 专属条款仅在使用对应技术栈时应用，不向其他框架强加不兼容约束。

优先级：用户明确需求和项目已正式采纳的规范 / ADR → 本规范 → 框架默认约定。

## 开始前确认

开始前确认本次页面/组件范围、需求或设计稿来源、目标技术栈与脚手架（shadcn-admin 衍生项目、Vite SPA、Taro H5/小程序端、Next.js 或其他），不默认原型、旧文档或现有代码永远权威。代码用于说明当前实现；与已确认设计不一致时记录差距，不反向改写设计。

## 关键规则

1. 组件分层：页面（路由层）只做组装与数据编排；可复用 UI 组件无业务副作用；业务逻辑进 hooks/services，不在组件体内堆叠。一个文件一个组件，命名与职责一致。
2. 类型契约：组件 props、API 响应、全局状态一律显式 TypeScript 类型；API 响应类型与后端契约字段一一对应，不随手 `any`；不把后端 VO 原样透传到展示层，按页面需要挑选与映射；枚举型字段按消费建模，前端区分取值（按值分支、逐值样式）时才定义与后端契约一致的字面量联合类型，纯展示与回传场景用 `string`。
3. 数据获取：请求统一走封装的服务层（统一 base URL、错误包络、超时与取消），不在组件里散落裸 `fetch`/`axios` 调用；加载、错误、空三态显式建模；列表与表单处理竞态（去重、取消上次请求），不做「看起来能跑」的时序假设。
4. 路由与状态：可安全公开的路由状态（页码、非敏感筛选、抽屉弹窗回退）进 URL，刷新与分享不丢；敏感条件及不适合分享的选中状态放受控会话或组件状态；服务端数据由请求层缓存管理，客户端 UI 状态能靠 props、URL 或组件局部解决的不引入全局 store；引入状态库须说明理由并只在一处定义。
5. 表单与校验：表单用受控校验库承载（react-hook-form + zod 等按项目脚手架），schema 与类型契约同源，字段规则（必填、长度、格式、取值域）与后端契约对齐，不一致以后端契约为准并反馈修正；前置校验错误标在字段旁，高危操作确认并设计恢复或审计，细则见交互基线。前端校验只改善交互，不替代后端对所有外部输入的独立校验和授权。
6. 错误与文案：国际化是系统基本要求——文案资源最低双语 `zh-CN`（默认）与 `en-US`，项目初始化即引入双语骨架，不在组件里硬编码任何语言的句子；前端只翻译自己生成的界面文案，响应中系统生成的描述性文案与枚举展示名由后端按 locale 给出译文、前端原样展示，不按 key 二次翻译（生成方判据与 key 生命周期以 mv-backend-standards spring-guide「国际化」为唯一全文源）；枚举取值全集（筛选、下拉）走枚举字典端点取得，不维护「取值 → 展示名」映射表；`code` 走前端文案资源映射通用描述；错误边界兜底，不白屏、不吞错。
7. 构建与环境变量：区分编译期固化与运行时注入——`VITE_*`、`TARO_APP_*` 等前端前缀变量会被打进产物，不放环境差异配置、密钥或分环境 API 地址；跨环境配置走运行时注入或相对路径（与 mv-image-builder 的构建期固化条款同源）。
8. 安全基线：不将未消毒内容注入 `dangerouslySetInnerHTML` 等等价通道；不把密钥、内网地址、调试开关打进前端包；新依赖先过 mv-tech-stack-baseline 的依赖引入评估再进。跨栈安全政策、数据分级与安全评审见 mv-security-standards，本节只保留前端实现边界。
9. 样式与设计系统：样式方案同一项目不混用多套；shadcn/ui 项目经 CLI 增改组件、走 CSS 变量主题令牌（语义色、间距），不硬编码色值绕开令牌；间距、色彩走项目设计令牌，不散落魔法数值；视觉还原以设计稿为准，本规范不定义视觉风格。
10. 交互与体验基线：页面布局范式稳定、信息层级清晰；交互元素状态完整、操作即时反馈；空/错/加载异常页面完备；用词全站统一；色彩用于区分状态而非装饰；键盘可达并按项目约定适配多分辨率。页面级条款见 [references/ux-interaction-guide.md](references/ux-interaction-guide.md)。
11. 最小变更与测试：改动现有系统保持最小必要变更，新产生的死代码、未用 import 一律删除；业务逻辑与行为改动写或更新对应测试（组件渲染/工具函数单测），使用项目现有测试框架，不为规范而更换框架；测试分层策略与覆盖口径按 mv-test-standards 关键规则执行，组件与交互测试写法见其 frontend-testing。

## 详细参考

框架中立主体见 [references/frontend-guide.md](references/frontend-guide.md)；Vite SPA 与 shadcn-admin 衍生项目并读 [references/vite-spa-guide.md](references/vite-spa-guide.md)；Taro H5/小程序端并读 [references/taro-guide.md](references/taro-guide.md)；使用 Next.js 时并读 [references/nextjs-guide.md](references/nextjs-guide.md)；涉及页面布局、交互流程、表单容错、异常态与可访问性时并读 [references/ux-interaction-guide.md](references/ux-interaction-guide.md)；涉及可访问性验收与性能预算时并读 [references/accessibility-performance.md](references/accessibility-performance.md)。规范中的举例和阈值不应覆盖项目实际框架版本、性能特征或已确立基线。

## 输出

在交付说明中列出关键规范决策、针对本次变更的遵循/偏离原因、实际应用的框架条款和执行的验证结果；结合实际页面逐项标注发现或无法排除的风险点、影响及对应优化方案，区分已完成与待验证，不泛泛输出整本规范。

## 自动验证与边界

优先运行项目已有检查（lint、typecheck、既有测试脚本）；没有配置的检查如实报告未执行，不虚构成功。出包与镜像构建归 mv-image-builder；技术栈选型与版本基线归 mv-tech-stack-baseline；系统架构与集成决策归 mv-architecture-standards；安全政策与安全评审归 mv-security-standards；工程文档与图件归 mv-engineering-doc-writer。静态规范和自动检查不能互相替代。

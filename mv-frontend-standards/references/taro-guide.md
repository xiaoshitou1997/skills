# Taro H5/小程序条款

项目使用 Taro（React 语法）开发 H5 或微信小程序端时并读本文件；通用条款见 [frontend-guide.md](frontend-guide.md)。与项目已确立基线冲突时以项目为准。

## 渲染目标与工程形态

- 编译目标按项目确认（weapp、h5）；平台分支经 `process.env.TARO_ENV` 判定收敛在适配层，不在业务组件内散布条件编译注释。
- 路由与页面按 Taro 约定组织（`app.config` 页面注册、tabBar 配置）；路由参数经实例参数显式传递，页面间通信走事件或全局状态，不隐式共享可变单例。
- 环境变量用 `TARO_APP_` 前缀（会被打进产物），约束与 `VITE_*` 一致：只放无环境差异的公开常量，分环境 API 地址与敏感值走运行时注入或相对路径。

## 请求层与类型

- 请求统一走 `Taro.request` 封装的服务层：统一 base URL、包络解析（对齐后端 `code`/`message`/`data`）、超时与取消；不在组件内散落裸调用与硬编码地址。
- API 类型与枚举字典消费规则与 Web 端同源：类型来源见 mv-project-scaffold「共享契约与类型同步」，枚举字典端点消费见 frontend-guide；小程序端不另行维护一套错误语义。

## 样式与交互

- 尺寸用 rpx 并以 750 设计稿为基准；安全区（刘海屏、底部横条）经 safe-area 适配；H5 端移动适配参照 [ux-interaction-guide.md](ux-interaction-guide.md) 多分辨率条款。
- 小程序样式默认组件内生效，全局样式与主题令牌集中在 app 级样式；色彩走项目设计令牌，不跨端硬编码色值。

## 平台差异与禁用清单

- 小程序无 DOM/BOM：不用 `window`、`document` 直接操作，经 `Taro.*` API 或适配层承担；`wx.*` 原生 API 调用收敛在适配层并做 H5 fallback 判定，业务代码不直接触碰平台 API。
- 支付、登录、存储等敏感能力经适配层注入；H5 与小程序行为差异由适配层的测试覆盖（测试条款见 mv-test-standards）。

## 包体与分包

- 主包只放核心页面与公共资源，非核心业务分包加载；分包边界按业务域划分并在 `app.config` 显式声明。
- 静态资源进 CDN 或对象存储，不打包进小程序包体；包体超限先减资源再谈分包重构。

本文只覆盖 Taro 工程条款；渲染目标对应的镜像构建与部署契约归 mv-image-builder 与 mv-container-deploy，技术栈选型归 mv-tech-stack-baseline。

# MyBatis-Plus 持久层条款

项目使用 MyBatis-Plus 时并读本文件；通用数据访问条款见 [java-guide.md](java-guide.md)。与项目已确立基线冲突时以项目为准。

- 含数字或特殊分隔的属性名要核对实际列映射，必要时显式 `@TableField`。
- 枚举映射用 `@EnumValue`/`IEnum` 或项目既有 TypeHandler，遵循项目已确立的映射方式，同一项目不混用方案。
- 软删除、枚举和唯一键形状遵循项目基线，不将单个项目约定推广为通用 DDL 规则。
- 分页优先用项目已配置的分页插件（如 `PaginationInnerInterceptor`），不手拼 LIMIT 偏移（新增条款，默认行为，可按项目既有分页方式覆盖）。

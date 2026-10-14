# JPA 持久层条款

项目使用 JPA/Hibernate 时并读本文件；通用数据访问条款见 [java-guide.md](java-guide.md)。与项目已确立基线冲突时以项目为准。

- 枚举持久化用 `@Enumerated(EnumType.STRING)` 保证存储值可读；同一项目不混用映射方案。
- 查询按需取字段：列表与报表场景用投影（DTO projection）替代实体全字段查询，即 `select *` 的同等约束。
- 关联加载显式化：需要关联数据时用 fetch join 或 `@EntityGraph` 明确获取路径，默认保持懒加载，避免在事务外触发懒加载异常（新增条款，默认行为，可按项目既有取数风格覆盖）。

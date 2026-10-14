"""触发契约用例：每条用例是一个用户请求与期望的路由结果。

- kind='positive'：query 应触发 skill 字段指定的 skill。
- kind='negative'：query 不得触发 skill 字段指定的 skill；instead 给出
  预期的正确去向，缺省表示任何 skill 都不应触发。

query 按用户真实表述风格编写，自含上下文，不依赖具体仓库内容。
运行器见 run_trigger_evals.py（需 claude CLI，按用例消耗 token）；
`python3 tests/run_trigger_evals.py --list` 可离线查看用例矩阵。
"""

CASES = [
    # --- mv-toolchain-manager：宿主工具链，不含构建出包与镜像内安装 ---
    {'skill': 'mv-toolchain-manager', 'kind': 'positive',
     'query': '本机没有 Java 17，项目 .java-version 要求 17，帮我准备一下开发环境'},
    {'skill': 'mv-toolchain-manager', 'kind': 'positive',
     'query': 'npm install 报 EBADENGINE，说当前 Node 版本不满足项目要求，怎么处理'},
    {'skill': 'mv-toolchain-manager', 'kind': 'positive',
     'query': '这个项目该用 npm、pnpm 还是 yarn？按项目约定帮我确认'},
    {'skill': 'mv-toolchain-manager', 'kind': 'positive',
     'query': '把本地开发用的 JDK 切到 21，不要污染全局环境'},
    {'skill': 'mv-toolchain-manager', 'kind': 'negative', 'instead': 'mv-wsl-build-deploy',
     'query': '帮我构建 jar 包并部署到 dev 环境'},
    {'skill': 'mv-toolchain-manager', 'kind': 'negative', 'instead': 'mv-wsl-build-deploy',
     'query': '在 Docker 镜像里装 Node 20 用于构建前端'},

    # --- mv-wsl-build-deploy：出包/本地调测/部署晋级，不含宿主工具链与 Git 发布 ---
    {'skill': 'mv-wsl-build-deploy', 'kind': 'positive',
     'query': '这次改动在本地跑一下，我要打断点调试接口'},
    {'skill': 'mv-wsl-build-deploy', 'kind': 'positive',
     'query': '构建出包并部署到 dev 环境'},
    {'skill': 'mv-wsl-build-deploy', 'kind': 'positive',
     'query': 'dev 容器起不来，帮我排查部署失败的原因'},
    {'skill': 'mv-wsl-build-deploy', 'kind': 'positive',
     'query': 'dev 验证通过了，把同一镜像晋级到生产'},
    {'skill': 'mv-wsl-build-deploy', 'kind': 'negative', 'instead': 'mv-toolchain-manager',
     'query': '本机缺 Java 17，帮我装一个'},
    {'skill': 'mv-wsl-build-deploy', 'kind': 'negative', 'instead': 'mv-git-commit-push',
     'query': '把这些改动提交并推送'},
    {'skill': 'mv-wsl-build-deploy', 'kind': 'negative', 'instead': 'mv-engineering-doc-writer-reviewer',
     'query': '把这次生产升级的步骤整理成一份可执行的 MOP 文档'},

    # --- mv-git-commit-push：发布动作，不含概念解释与经验沉淀 ---
    {'skill': 'mv-git-commit-push', 'kind': 'positive',
     'query': '提交并推送这次的改动'},
    {'skill': 'mv-git-commit-push', 'kind': 'positive',
     'query': '把工作区的改动拆成几个原子 commit 再一起推送'},
    {'skill': 'mv-git-commit-push', 'kind': 'positive',
     'query': '创建一个到 main 的 PR，并查看 CI 检查结果'},
    {'skill': 'mv-git-commit-push', 'kind': 'positive',
     'query': 'PR 上有一个 check 失败了，帮我看看原因'},
    {'skill': 'mv-git-commit-push', 'kind': 'negative',
     'query': '解释一下 git rebase 和 merge 的区别，什么时候用哪个'},
    {'skill': 'mv-git-commit-push', 'kind': 'negative', 'instead': 'mv-skill-curator',
     'query': '把刚才聊的这套提交约定沉淀进 skills 仓库'},

    # --- mv-spring-boot-standards：Spring Boot 编码/审查，不含部署与非 Spring 框架 ---
    {'skill': 'mv-spring-boot-standards', 'kind': 'positive',
     'query': '在 Spring Boot 项目里新增一个创建订单的 REST 接口，按规范分层实现'},
    {'skill': 'mv-spring-boot-standards', 'kind': 'positive',
     'query': '审查这段 Spring Boot Service 代码，事务边界和异常处理是否合规'},
    {'skill': 'mv-spring-boot-standards', 'kind': 'positive',
     'query': '这个列表查询接口有 N+1 问题吗？按规范应该怎么改'},
    {'skill': 'mv-spring-boot-standards', 'kind': 'positive',
     'query': '为这个接口设计错误码枚举和用户可见文案的国际化方案'},
    {'skill': 'mv-spring-boot-standards', 'kind': 'negative', 'instead': 'mv-wsl-build-deploy',
     'query': '把这个 Spring Boot 项目部署到 dev 容器'},
    {'skill': 'mv-spring-boot-standards', 'kind': 'negative',
     'query': '用 Quarkus 写一个 REST 接口示例'},

    # --- mv-engineering-doc-writer-reviewer：工程文档产出/评审，不含按文档执行操作 ---
    {'skill': 'mv-engineering-doc-writer-reviewer', 'kind': 'positive',
     'query': '把这段需求讨论整理成一份可评审的 PRD'},
    {'skill': 'mv-engineering-doc-writer-reviewer', 'kind': 'positive',
     'query': '评审这份 HLD 架构设计文档，指出缺失的决策和前后矛盾'},
    {'skill': 'mv-engineering-doc-writer-reviewer', 'kind': 'positive',
     'query': '为本次生产数据库升级编写一份带检查点和回滚步骤的 MOP'},
    {'skill': 'mv-engineering-doc-writer-reviewer', 'kind': 'positive',
     'query': '给新接口写一份 API 文档，包含字段说明、错误码和示例'},
    {'skill': 'mv-engineering-doc-writer-reviewer', 'kind': 'negative', 'instead': 'mv-wsl-build-deploy',
     'query': '按照 MOP 把这次生产升级实际执行一遍'},
    {'skill': 'mv-engineering-doc-writer-reviewer', 'kind': 'negative', 'instead': 'mv-skill-curator',
     'query': '把这套文档写作约定沉淀成仓库里的 skill'},
    {'skill': 'mv-engineering-doc-writer-reviewer', 'kind': 'negative', 'instead': 'mv-git-commit-push',
     'query': '帮这次的改动写一条规范的提交信息'},

    # --- mv-skill-curator：沉淀进本仓库，不含业务实现与闲聊 ---
    {'skill': 'mv-skill-curator', 'kind': 'positive',
     'query': '把我们团队刚确认的这条分支命名约定加进 skills 仓库'},
    {'skill': 'mv-skill-curator', 'kind': 'positive',
     'query': '这几条聊天里的流程片段，判断该并进哪个现有 skill 还是新建'},
    {'skill': 'mv-skill-curator', 'kind': 'positive',
     'query': '消化一下 INBOX.md 里积压的碎片条目'},
    {'skill': 'mv-skill-curator', 'kind': 'negative', 'instead': 'mv-spring-boot-standards',
     'query': '帮我写一个 Spring Boot Controller 的单元测试'},
    {'skill': 'mv-skill-curator', 'kind': 'negative',
     'query': '今天天气不错，随便聊聊'},
]

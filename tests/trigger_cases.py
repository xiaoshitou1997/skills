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
    {'skill': 'mv-toolchain-manager', 'kind': 'negative', 'instead': 'mv-container-deploy',
     'query': '帮我构建 jar 包并部署到 dev 环境'},
    {'skill': 'mv-toolchain-manager', 'kind': 'negative', 'instead': 'mv-image-build',
     'query': '在 Docker 镜像里装 Node 20 用于构建前端'},

    # --- mv-local-debug：本机（宿主）直启调试，零 WSL 零镜像，不含构建出包、容器与部署 ---
    {'skill': 'mv-local-debug', 'kind': 'positive',
     'query': '这次改动在本地跑一下，我要打断点调试接口'},
    {'skill': 'mv-local-debug', 'kind': 'positive',
     'query': '不要走容器，直接在本机把服务跑起来，我开着终端看日志'},
    {'skill': 'mv-local-debug', 'kind': 'positive',
     'query': '宿主构建报 Unable to establish loopback connection，帮我排查一下'},
    {'skill': 'mv-local-debug', 'kind': 'positive',
     'query': '本地起 dev server 联调前端，热更新好像没生效'},
    {'skill': 'mv-local-debug', 'kind': 'negative', 'instead': 'mv-toolchain-manager',
     'query': '本机缺 Java 17，帮我装一个'},
    {'skill': 'mv-local-debug', 'kind': 'negative', 'instead': 'mv-image-build',
     'query': '帮我把这个项目打成 Docker 镜像'},
    {'skill': 'mv-local-debug', 'kind': 'negative', 'instead': 'mv-container-deploy',
     'query': '在 WSL 容器里把这个镜像跑起来看看'},
    {'skill': 'mv-local-debug', 'kind': 'negative', 'instead': 'mv-git-publisher',
     'query': '把这些改动提交并推送'},

    # --- mv-image-build：宿主出包 + WSL 瘦镜像构建，只构建不运行 ---
    {'skill': 'mv-image-build', 'kind': 'positive',
     'query': '帮我把这个项目打成 Docker 镜像，出个包'},
    {'skill': 'mv-image-build', 'kind': 'positive',
     'query': '出个镜像包就行，先不用部署'},
    {'skill': 'mv-image-build', 'kind': 'positive',
     'query': 'WSL 里构建镜像一直卡在下载依赖，帮我排查'},
    {'skill': 'mv-image-build', 'kind': 'negative', 'instead': 'mv-container-deploy',
     'query': '在 WSL 容器里验证一下这个镜像能不能正常启动'},
    {'skill': 'mv-image-build', 'kind': 'negative', 'instead': 'mv-local-debug',
     'query': '不走容器，直接在本机跑起来调试'},
    {'skill': 'mv-image-build', 'kind': 'negative', 'instead': 'mv-toolchain-manager',
     'query': '把本机开发用的 JDK 切到 21'},

    # --- mv-container-deploy：部署/晋级/回滚，不含出包与本地调测 ---
    {'skill': 'mv-container-deploy', 'kind': 'positive',
     'query': '构建出包并部署到 dev 环境'},
    {'skill': 'mv-container-deploy', 'kind': 'positive',
     'query': 'dev 容器起不来，帮我排查部署失败的原因'},
    {'skill': 'mv-container-deploy', 'kind': 'positive',
     'query': 'dev 验证通过了，把同一镜像晋级到生产'},
    {'skill': 'mv-container-deploy', 'kind': 'positive',
     'query': '线上发布有问题，把上一个版本回滚回去'},
    {'skill': 'mv-container-deploy', 'kind': 'positive',
     'query': '在 WSL 容器里验证一下这个镜像能不能正常启动'},
    {'skill': 'mv-container-deploy', 'kind': 'negative', 'instead': 'mv-image-build',
     'query': '出个镜像包就行，先不用部署'},
    {'skill': 'mv-container-deploy', 'kind': 'negative', 'instead': 'mv-engineering-doc-writer',
     'query': '把这次生产升级的步骤整理成一份可执行的 MOP 文档'},

    # --- mv-git-publisher：发布动作，不含概念解释与经验沉淀 ---
    {'skill': 'mv-git-publisher', 'kind': 'positive',
     'query': '提交并推送这次的改动'},
    {'skill': 'mv-git-publisher', 'kind': 'positive',
     'query': '把工作区的改动拆成几个原子 commit 再一起推送'},
    {'skill': 'mv-git-publisher', 'kind': 'positive',
     'query': '创建一个到 main 的 PR，并查看 CI 检查结果'},
    {'skill': 'mv-git-publisher', 'kind': 'positive',
     'query': 'PR 上有一个 check 失败了，帮我看看原因'},
    {'skill': 'mv-git-publisher', 'kind': 'negative',
     'query': '解释一下 git rebase 和 merge 的区别，什么时候用哪个'},
    {'skill': 'mv-git-publisher', 'kind': 'negative',
     'query': '把刚才聊的这套提交约定沉淀进 skills 仓库'},

    # --- mv-java-backend-standards：Java 后端编码/审查，条款分框架应用，不含技术栈选型与部署 ---
    {'skill': 'mv-java-backend-standards', 'kind': 'positive',
     'query': '在 Spring Boot 项目里新增一个创建订单的 REST 接口，按规范分层实现'},
    {'skill': 'mv-java-backend-standards', 'kind': 'positive',
     'query': '审查这段 Spring Boot Service 代码，事务边界和异常处理是否合规'},
    {'skill': 'mv-java-backend-standards', 'kind': 'positive',
     'query': '这个列表查询接口有 N+1 问题吗？按规范应该怎么改'},
    {'skill': 'mv-java-backend-standards', 'kind': 'positive',
     'query': '为这个接口设计错误码枚举和用户可见文案的国际化方案'},
    {'skill': 'mv-java-backend-standards', 'kind': 'negative', 'instead': 'mv-container-deploy',
     'query': '把这个 Spring Boot 项目部署到 dev 容器'},
    {'skill': 'mv-java-backend-standards', 'kind': 'positive',
     'query': '用 Quarkus 写一个 REST 接口，按通用后端规范分层实现'},
    {'skill': 'mv-java-backend-standards', 'kind': 'negative', 'instead': 'mv-tech-stack-standards',
     'query': '新项目该选 MyBatis-Plus 还是 Spring Data JPA？'},

    # --- mv-tech-stack-standards：选型/基线/依赖决策，不含写代码、装工具与部署 ---
    {'skill': 'mv-tech-stack-standards', 'kind': 'positive',
     'query': '新建一个后端服务，帮我定技术栈和版本基线'},
    {'skill': 'mv-tech-stack-standards', 'kind': 'positive',
     'query': '项目里要引入一个新的 Redis 客户端库，按约定该怎么评估'},
    {'skill': 'mv-tech-stack-standards', 'kind': 'positive',
     'query': '盘点一下这个项目现在用了哪些框架，版本都锁定在哪里'},
    {'skill': 'mv-tech-stack-standards', 'kind': 'negative', 'instead': 'mv-java-backend-standards',
     'query': '写一个分页查询接口，按规范处理事务和异常'},
    {'skill': 'mv-tech-stack-standards', 'kind': 'negative', 'instead': 'mv-toolchain-manager',
     'query': '本机装个 Node 20 并把默认版本切过去'},
    {'skill': 'mv-tech-stack-standards', 'kind': 'negative', 'instead': 'mv-container-deploy',
     'query': '把这个服务打包部署到 dev 环境'},

    # --- mv-engineering-doc-writer：工程文档产出/评审，不含按文档执行操作 ---
    {'skill': 'mv-engineering-doc-writer', 'kind': 'positive',
     'query': '把这段需求讨论整理成一份可评审的 PRD'},
    {'skill': 'mv-engineering-doc-writer', 'kind': 'positive',
     'query': '评审这份 HLD 架构设计文档，指出缺失的决策和前后矛盾'},
    {'skill': 'mv-engineering-doc-writer', 'kind': 'positive',
     'query': '为本次生产数据库升级编写一份带检查点和回滚步骤的 MOP'},
    {'skill': 'mv-engineering-doc-writer', 'kind': 'positive',
     'query': '给新接口写一份 API 文档，包含字段说明、错误码和示例'},
    {'skill': 'mv-engineering-doc-writer', 'kind': 'negative', 'instead': 'mv-container-deploy',
     'query': '按照 MOP 把这次生产升级实际执行一遍'},
    {'skill': 'mv-engineering-doc-writer', 'kind': 'negative',
     'query': '把这套文档写作约定沉淀成仓库里的 skill'},
    {'skill': 'mv-engineering-doc-writer', 'kind': 'negative', 'instead': 'mv-git-publisher',
     'query': '帮这次的改动写一条规范的提交信息'},

    # --- mv-unattended-watch：离场无人值守模式开关与值守，不含具体领域操作 ---
    {'skill': 'mv-unattended-watch', 'kind': 'positive',
     'query': '我要睡觉了，剩下的活儿你全权处理，别再问我'},
    {'skill': 'mv-unattended-watch', 'kind': 'positive',
     'query': '全权交给AI，后面的所有疑问你自己做决定'},
    {'skill': 'mv-unattended-watch', 'kind': 'positive',
     'query': '我要下班了，无人值守跑完剩下的任务，明天我来看结果'},
    {'skill': 'mv-unattended-watch', 'kind': 'negative', 'instead': 'mv-git-publisher',
     'query': '提交并推送这次的改动'},
    {'skill': 'mv-unattended-watch', 'kind': 'negative', 'instead': 'mv-container-deploy',
     'query': '构建出包并部署到 dev 环境'},
    {'skill': 'mv-unattended-watch', 'kind': 'negative',
     'query': '解释一下上下文压缩之后上下文里的约定为什么会丢'},

    # --- mv-nfr-intake：开工前非功能性需求采集确认，不含编码条款、选型与正式文档写作 ---
    {'skill': 'mv-nfr-intake', 'kind': 'positive',
     'query': '新项目要启动，先把用户规模、TPS、网络平面、部署约束这些非功能性需求问清楚再开工'},
    {'skill': 'mv-nfr-intake', 'kind': 'positive',
     'query': '系统要对接三个外部系统，调用频率差很多，网络也不归我们管，开工前把这些约束理一遍'},
    {'skill': 'mv-nfr-intake', 'kind': 'positive',
     'query': '这个新需求开发前，看看 NFR 画像还缺什么需要补的'},
    {'skill': 'mv-nfr-intake', 'kind': 'positive',
     'query': 'QPS 我们答不上来，按保守默认来，标成假设让我确认'},
    {'skill': 'mv-nfr-intake', 'kind': 'negative', 'instead': 'mv-java-backend-standards',
     'query': '审查这段 Service 代码的事务边界和异常处理是否合规'},
    {'skill': 'mv-nfr-intake', 'kind': 'negative', 'instead': 'mv-engineering-doc-writer',
     'query': '把容量和网络约束整理成正式的 HLD 章节'},
    {'skill': 'mv-nfr-intake', 'kind': 'negative',
     'query': '把注释里的错别字改一下'},]

# 镜像源 (mirrors)

镜像默认关闭。启用后，镜像 URL 会**前置**到每个工具的候选列表，官方源仍作为兜底保留在列表末尾。

## 启用方式

两种等价方式（CLI flag 优先级高于 env）：

```bash
# 1) 环境变量（推荐，跨多次调用稳定）
export BTC_MIRROR=cn
python3 "${SKILL_ROOT}/scripts/installer/runtime_cli.py" ensure --jdk 21

# 2) 命令行 flag（仅当前调用生效）
python3 "${SKILL_ROOT}/scripts/installer/runtime_cli.py" --mirror cn ensure --jdk 21

# 显式关闭（即使 BTC_MIRROR 已设置）
python3 "${SKILL_ROOT}/scripts/installer/runtime_cli.py" --mirror none ensure --jdk 21
```

## 当前可用镜像

| key | Node | JDK | Maven | Gradle |
|-----|------|-----|-------|--------|
| `cn` | `cdn.npmmirror.com/binaries/node` | `mirrors.tuna.tsinghua.edu.cn/Adoptium` | `mirrors.tuna.tsinghua.edu.cn/apache/maven` | `mirrors.cloud.tencent.com/gradle` |

这些是第三方托管的上游镜像，不应称为官方源。可用性、同步时效和内容完整性需自行验证；安装器的可达性预检不等于校验发行方摘要或签名。配置见 `scripts/installer/mirrors.py`，新增镜像应先审查来源与发行文件校验机制。

## 候选顺序

启用 `cn` 后，`sources.<tool>_urls()` 返回的列表顺序：

| 工具 | 顺序 |
|------|------|
| Node | `[npmmirror, nodejs.org]` |
| JDK | `[tuna Adoptium, api.adoptium.net (官方 API)]` |
| Maven | `[tuna apache, dlcdn.apache.org, archive.apache.org]` |
| Gradle | `[tencent gradle, services.gradle.org]` |

关闭镜像时，候选列表不含 mirror URL，与历史行为完全一致。

## 两阶段下载（避免 404 重试）

`download.install_portable` 走严格的两阶段流程，**禁止"GET 失败再换下一个"**：

```
Phase 1 (probe): 对所有候选 URL 逐个发 HEAD（服务器不支持 HEAD 则改 1-byte ranged GET）。
                 只有响应 200 的 URL 进入 validated 列表。
                 404/401/403 等任何非 200 直接 reject，且会打印 [skip] 日志。

Phase 2 (fetch): 对 validated 列表首个 URL 发 GET + 解压。
                 若仅因网络中断等传输错误失败，才尝试 validated 列表里的下一个。
                 传输错误重试 ≠ 404 重试：URL 已经被证明可下载，只是本次传输失败。
```

`SKILL.md` 的硬约束"网络失败时如实报错，给出 URL 与 HTTP 状态"在 probe 阶段就落实了——所有拒绝原因都带 HTTP code 或网络错误描述，输出在 stderr 的 `[skip]` 行里。

## JDK 镜像的特别处理

官方 JDK URL 是 Adoptium API endpoint，会 302 重定向到带签名 token 的 GitHub release-assets（短期有效、不能直接镜像）。处理：

1. `_jdk_filename(feature)` 先 HEAD 官方 API，跟随重定向，从最终 URL 的 `response-content-disposition` 解析出真实文件名（如 `OpenJDK21U-jdk_x64_windows_hotspot_21.0.11_10.zip`）。
2. 用该文件名拼接镜像 URL：`https://mirrors.tuna.tsinghua.edu.cn/Adoptium/21/jdk/x64/windows/OpenJDK21U-jdk_x64_windows_hotspot_21.0.11_10.zip`。
3. 候选列表：`[镜像 URL, 官方 API URL]`。两者都过 probe，命中谁就下载谁。

如果 `_jdk_filename` 因网络问题失败，会跳过 mirror URL，仅保留官方 API URL，并在 stderr 打印 warning。

## 验证 mirror 实际被使用

```bash
python3 "${SKILL_ROOT}/scripts/installer/runtime_cli.py" --mirror cn ensure --jdk 21 2>&1 1>/dev/null | grep -E 'probing|downloading'
```

输出示例：

```
  probing 2 candidate URL(s) for Temurin JDK 21
    [ok]    https://mirrors.tuna.tsinghua.edu.cn/Adoptium/21/jdk/x64/windows/OpenJDK21U-jdk_x64_windows_hotspot_21.0.11_10.zip (205073954 bytes)
    [ok]    https://api.adoptium.net/v3/binary/latest/21/ga/windows/x64/jdk/hotspot/normal/eclipse (...)
  downloading Temurin JDK 21
    https://mirrors.tuna.tsinghua.edu.cn/Adoptium/21/jdk/x64/windows/...   <-- 走了 mirror
```

## 不引入镜像策略的回退

如果 mirror URL probe 失败（404、网络不可达、证书错误），**不会**重试 GET，而是直接跳过该 mirror，使用 validated 列表中下一个（通常是官方源）。这与"GET 失败再换"的区别：

| 场景 | 旧的 GET-fallback（已废弃） | 新的 probe-then-GET |
|------|-----------------------------|----------------------|
| mirror 404 | 浪费一次完整 GET（可能等几十秒到 200MB）才发现 404 | probe 阶段秒级判定，从未对 mirror 发 GET |
| mirror 网络不可达 | GET 阻塞到 timeout 才切换 | probe 30s timeout 内判定 |
| mirror 中途断流 | 失败后再切回官方，前半段流量浪费 | probe 已通过 → 这次 GET 失败 → 切换到下一个已 validated 的 URL（合理） |

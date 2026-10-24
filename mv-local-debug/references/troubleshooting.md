# 宿主调测常见故障

本文件收录 mv-local-debug 宿主链路（直启与宿主构建）的高频故障与判定方法；调测停滞时先按症状对照本表，再用 `doctor.py` 复核环境。只覆盖宿主范围；镜像构建链路故障见 `mv-image-build`，部署与容器运行故障见 `mv-container-deploy`。

## 端口占用

- 宿主直启前停掉占用同端口的进程（IDEA 网关、vite dev server 等）；间歇性 `address already in use` 先查这一层。
- Windows 宿主用 `netstat -ano | findstr <端口>`，Linux/macOS 宿主用 `ss -ltnp | grep <端口>` 或 `lsof -i :<端口>` 查占用进程并停掉或改端口，连不通时再核对防火墙（ufw/firewalld/安全组）。

故障不在本表时回到 SKILL.md 工作流逐步取证；镜像与容器侧问题移交 `mv-image-build` 与 `mv-container-deploy`。

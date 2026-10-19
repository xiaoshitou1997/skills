#!/usr/bin/env python3
"""Read-only, stdlib-only project/environment diagnostics."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess


def version(*cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        detail = (p.stdout or p.stderr).strip().splitlines()
        return {"ok": p.returncode == 0, "detail": (detail[0][:160] if detail else "")}
    except (OSError, subprocess.TimeoutExpired):
        return {"ok": False, "detail": "not available"}


def wsl_distro():
    """First available WSL distro name, or empty string; tolerant of UTF-16 output."""
    try:
        p = subprocess.run(["wsl.exe", "-l", "-q"], capture_output=True, timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if p.returncode != 0:
        return ""
    for enc in ("utf-16-le", "utf-8"):
        names = [line.strip() for line in p.stdout.decode(enc, "ignore").replace("\r", "").split("\n") if line.strip()]
        if names:
            return names[0]
    return ""


def _nio_smoke():
    """Selector.open() smoke test from the current process chain.

    Some security software hooks java by process chain (agent shells like Git Bash),
    breaking Selector with 'Unable to establish loopback connection' — which makes
    host gradle/mvn builds fail no matter the toolchain. Detects it in seconds."""
    import tempfile
    src = Path(tempfile.gettempdir()) / "ff_build_chain_smoke.java"
    try:
        src.write_text(
            "import java.nio.channels.Selector;"
            "public class ff_build_chain_smoke{"
            "public static void main(String[] a) throws Exception{"
            "Selector.open(); System.out.println(\"CHAIN-OK\");}}",
            encoding="utf-8")
    except OSError:
        return {"ok": False, "detail": "cannot write temp probe"}
    try:
        p = subprocess.run(["java", str(src)], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return {"ok": False, "detail": "java probe failed to run"}
    finally:
        # 探针文件用完即清,不在临时目录留残留。
        try:
            src.unlink()
        except OSError:
            pass
    out = ((p.stdout or "") + (p.stderr or "")).strip()
    if "CHAIN-OK" in out:
        return {"ok": True, "detail": "clean chain"}
    lines = out.splitlines()
    detail = next((ln.strip() for ln in lines if "Exception" in ln), lines[-1] if lines else "no output")
    return {"ok": False, "detail": detail[:120]}


def _wsl_resources(distro):
    # 用 --exec 直接 exec:否则 wsl.exe 把余下参数拼接后交给默认 shell,引号会丢失。
    try:
        p = subprocess.run(["wsl.exe", "-d", distro, "--exec", "sh", "-c",
                            "nproc && grep MemTotal /proc/meminfo"],
                           capture_output=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return {"ok": False, "detail": "probe failed"}
    for enc in ("utf-8", "utf-16-le"):
        lines = [x.strip() for x in (p.stdout or b"").decode(enc, "ignore").replace("\r", "").split("\n") if x.strip()]
        if len(lines) >= 2 and lines[0].isdigit() and "MemTotal" in lines[1]:
            try:
                mem_mb = int(lines[1].split()[1]) // 1024
            except (ValueError, IndexError):
                continue
            cpus = int(lines[0])
            # 经验阈值:低于 8 核 / 12GB 时 Gradle/Maven 与镜像构建明显变慢;仅建议输出,不是门禁。
            ok = cpus >= 8 and mem_mb >= 12000
            return {"ok": ok, "detail": f"nproc={cpus}, mem={mem_mb // 1024}GB (low values: check ~/.wslconfig)"}
    return {"ok": False, "detail": "no data"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=".")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    root = Path(args.project).resolve()
    is_windows = os.name == "nt"
    command_names = (
        "git", "docker", "ssh", "gh", "gitleaks", "trivy", "node", "java", "mvn",
        "gradle", "python", "npm", "pnpm", "yarn", "uv",
    )
    commands = {key: {"available": shutil.which(key) is not None}
                for key in command_names}
    checks = {
        "git": version("git", "--version"),
        "docker": version("docker", "--version"),
        "docker_compose": version("docker", "compose", "version"),
        "gh": version("gh", "--version"),
        "node": version("node", "--version"),
        "java": version("java", "-version"),
        "maven": version("mvn", "--version"),
        "gradle": version("gradle", "--version"),
        "python": version("python", "--version"),
        "npm": version("npm", "--version"),
        "pnpm": version("pnpm", "--version"),
        "yarn": version("yarn", "--version"),
        "uv": version("uv", "--version"),
    }
    if is_windows:
        distro = wsl_distro()
        checks["wsl_distro"] = {"ok": bool(distro), "detail": distro or "no distro"}
        checks["wsl_docker"] = (version("wsl.exe", "-d", distro, "--exec", "docker", "--version")
                                if distro else {"ok": False, "detail": "not available"})
        if commands["java"]["available"]:
            checks["host_build_chain"] = _nio_smoke()
        if distro:
            checks["wsl_resources"] = _wsl_resources(distro)
    project = {name: (root / name).exists() for name in
               ("pom.xml", "build.gradle", "build.gradle.kts", "package.json", "Dockerfile.delivery",
                "compose.delivery.yml", ".dockerignore", ".env.dev", ".env.prod")}
    result = {"project": str(root), "commands": commands, "checks": checks, "files": project,
              "recommendations": []}
    if not checks["docker_compose"]["ok"]:
        result["recommendations"].append("Delivery requires Docker Engine and Compose v2")
    if is_windows and not checks["wsl_docker"]["ok"]:
        result["recommendations"].append(
            "Team rule: containers must run inside WSL on Windows; install WSL2 + Docker (wsl --install -d Ubuntu)")
    if not project[".dockerignore"]:
        result["recommendations"].append("Add .dockerignore before Docker delivery")
    if not commands["gh"]["available"]:
        result["recommendations"].append("Install/authenticate gh only if GitHub PR workflow is wanted")
    if is_windows and not checks.get("host_build_chain", {"ok": True})["ok"]:
        result["recommendations"].append(
            "Builds launched from this shell may fail (process-chain security hook, 'loopback connection'); "
            "run builds via templates/schtasks-build.cmd or have the user build manually")
    if is_windows and "wsl_resources" in checks and not checks["wsl_resources"]["ok"]:
        result["recommendations"].append(
            f"WSL resources constrained: {checks['wsl_resources']['detail']}")
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("Skills doctor:", root)
        for k, v in checks.items():
            print(f"  {k}: {'PASS' if v['ok'] else 'MISSING'} - {v['detail']}")
        for item in result["recommendations"]:
            print("  NOTE:", item)
    return 0  # Diagnostic, not a gate.


if __name__ == "__main__":
    raise SystemExit(main())

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


def _nio_smoke():
    """Selector.open() smoke test from the current process chain.

    Desktop-agent command-runner process chains on Windows can carry a filter that
    rejects AF_UNIX connect under AppData (bind passes, connect fails EINVAL); the
    JDK >=14 WEPoll selector wakeup pipe lives in java.io.tmpdir and hits it, breaking
    Selector with 'Unable to establish loopback connection' — host gradle/mvn builds
    fail no matter the toolchain. First-line workaround:
    JAVA_TOOL_OPTIONS='-Djdk.net.unixdomain.tmpdir=C:/Windows/Temp'
    (java.io.tmpdir alone does NOT work). Detects it in seconds."""
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=".")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    root = Path(args.project).resolve()
    is_windows = os.name == "nt"
    # 宿主只出包并上传:镜像与扫描都在构建点(服务器)完成,宿主侧只关心
    # 编译工具链、git 溯源与 SSH 上传通道。
    command_names = (
        "git", "ssh", "gh", "gitleaks", "node", "java", "mvn",
        "gradle", "python", "npm", "pnpm", "yarn", "uv",
    )
    commands = {key: {"available": shutil.which(key) is not None}
                for key in command_names}
    checks = {
        "git": version("git", "--version"),
        "ssh": version("ssh", "-V"),
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
    if is_windows and commands["java"]["available"]:
        checks["host_build_chain"] = _nio_smoke()
    project = {name: (root / name).exists() for name in
               ("pom.xml", "build.gradle", "build.gradle.kts", "package.json", "Dockerfile.delivery",
                "compose.delivery.yml", ".dockerignore", ".env.dev", ".env.prod")}
    result = {"project": str(root), "commands": commands, "checks": checks, "files": project,
              "recommendations": []}
    if not checks["ssh"]["ok"]:
        result["recommendations"].append(
            "镜像统一在构建点(服务器)构建:FF_BUILD_TARGET 走 SSH 通道,需要可用的 ssh 客户端")
    if not project[".dockerignore"]:
        result["recommendations"].append("Add .dockerignore before Docker delivery")
    if not commands["gh"]["available"]:
        result["recommendations"].append("Install/authenticate gh only if GitHub PR workflow is wanted")
    if is_windows and not checks.get("host_build_chain", {"ok": True})["ok"]:
        result["recommendations"].append(
            "Builds launched from this shell may fail (AF_UNIX connect blocked in agent process chain, 'loopback connection'); "
            "retry with JAVA_TOOL_OPTIONS='-Djdk.net.unixdomain.tmpdir=C:/Windows/Temp' (java.io.tmpdir will NOT work), "
            "then templates/schtasks-build.cmd or have the user build manually")
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

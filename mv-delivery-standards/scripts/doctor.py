#!/usr/bin/env python3
"""Read-only, stdlib-only project/environment diagnostics."""
import argparse
import json
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=".")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    root = Path(args.project).resolve()
    # 部署宿主只需 Git 与 SSH 客户端;Docker/Compose 在目标服务器侧,由 deploy-preflight.sh 经 SSH 校验。
    command_names = ("git", "ssh", "scp")
    commands = {key: {"available": shutil.which(key) is not None}
                for key in command_names}
    checks = {
        "git": version("git", "--version"),
        "ssh": version("ssh", "-V"),
    }
    project = {name: (root / name).exists() for name in
               ("compose.delivery.yml", ".dockerignore", ".env.dev", ".env.prod")}
    result = {"project": str(root), "commands": commands, "checks": checks, "files": project,
              "recommendations": []}
    if not commands["ssh"]["available"]:
        result["recommendations"].append("Delivery targets are reached over SSH; install an OpenSSH client")
    if not project[".dockerignore"]:
        result["recommendations"].append("Add .dockerignore before container delivery")
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

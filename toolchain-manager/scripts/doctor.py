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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=".")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    root = Path(args.project).resolve()
    commands = {key: {"available": shutil.which(key) is not None}
                for key in ("git", "docker", "ssh", "gh", "gitleaks", "trivy", "node", "java", "mvn")}
    checks = {"git": version("git", "--version"),
              "docker": version("docker", "--version"),
              "docker_compose": version("docker", "compose", "version"),
              "gh": version("gh", "--version")}
    project = {name: (root / name).exists() for name in
               ("pom.xml", "build.gradle", "build.gradle.kts", "package.json", "Dockerfile.delivery",
                "compose.delivery.yml", ".dockerignore", ".env.dev", ".env.prod")}
    result = {"project": str(root), "commands": commands, "checks": checks, "files": project,
              "recommendations": []}
    if not checks["docker_compose"]["ok"]:
        result["recommendations"].append("Delivery requires Docker Engine and Compose v2")
    if not project[".dockerignore"]:
        result["recommendations"].append("Add .dockerignore before Docker delivery")
    if not commands["gh"]["available"]:
        result["recommendations"].append("Install/authenticate gh only if GitHub PR workflow is wanted")
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

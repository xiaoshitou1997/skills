# Team Engineering Skills

[中文说明](README.md)

Team-reusable Agent Skills for Git publishing, WSL container build/debug/deploy, toolchains and engineering documentation. Each skill includes its own scripts and references and can be installed independently with the [skills CLI](https://github.com/vercel-labs/skills).

This collection contains team engineering practices, not an official product or certification from an agent, framework or endpoint-security vendor.

## Skills

| Skill | Scope |
| --- | --- |
| `orca-toolchain-manager` | Detect and prepare local JDK, Maven, Gradle and Node.js; respect project version managers and wrappers |
| `orca-wsl-build-deploy` | Build, run/debug locally, deploy dev/prod, promote and roll back through one WSL container pipeline |
| `orca-git-commit-push` | Prepare logical commits and push as one integral action; inspect or create GitHub PRs |
| `orca-spring-boot-standards` | Project-aware Spring Boot conventions; MyBatis-Plus guidance where applicable |
| `orca-engineering-doc-writer` | Write, rewrite and review PRD, HLD, LLD, RFC, API docs and production MOPs |
| `orca-skill-curator` | Distill casually shared work habits and workflows into this repo: triage, merge, split, refactor and validate |


“Reusable” means across this team's projects, not a universal standard for every company or team. Skills use confirmed team conventions as their baseline and leave business-specific details in each project. Team Git rules require pulling and resolving conflicts before committing, keeping linear history and avoiding merge commits.

## Maintenance principles

- Extract team-reusable methods, conventions and verification criteria from experience. Encode confirmed team rules directly rather than making them optional because other teams may differ. Do not copy project-specific business rules, fixed paths or credentials.
- Keep the current workflow in SKILL.md and load environment/framework details from references as needed. Update descriptions, examples, entry points and links together so obsolete instructions do not remain active.
- Report compilation, unit tests, mock integration and real-system integration separately. Static checks do not establish behavior; use scoped machine checks for recurring mechanical errors rather than accumulating reminders.

## Install

Install from this repository:

```bash
npx skills@latest add xiaoshitou1997/skills --list
npx skills@latest add xiaoshitou1997/skills
npx skills@latest add xiaoshitou1997/skills --skill orca-git-commit-push -g -a claude-code
# Local checkout: list skills without installing
npx skills@latest add . --list
```

The CLI supports multiple agents; select the target with `-a`. Skills are loaded according to the selected agent's behavior. Node.js is needed for the CLI. Python utilities need Python 3 (`python3`, `python` or `py -3`, depending on the environment); shell utilities need Bash and their documented tools.

## Run bundled tools

Locate the installed skill through its loaded `SKILL.md`. `SKILL_ROOT` below is an explicitly assigned absolute path, not an agent-provided variable. Run project-oriented commands from your application repository:

```bash
SKILL_ROOT="/absolute/path/to/orca-toolchain-manager"
python3 "$SKILL_ROOT/scripts/doctor.py" --project .

SKILL_ROOT="/absolute/path/to/orca-git-commit-push"
python3 "$SKILL_ROOT/scripts/stage_audit.py"
bash "$SKILL_ROOT/scripts/pr.sh" view
```

Commit language and format follow the user and repository conventions. The default in the absence of conventions is Chinese Conventional Commits. Existing staged changes are preserved and inspected before committing.

## WSL build & deploy

`orca-wsl-build-deploy` unifies local run/debug and dev/prod delivery in one WSL container pipeline. Built-in templates cover Java executable JARs and static Node frontends. Gradle projects build through a resident daemon container by default for incremental speed; `FF_GRADLE_DAEMON=0` opts back into in-image multistage builds. Other architectures need project-owned Dockerfile/Compose configuration. Prepare `.dockerignore` and untracked `.env.dev`/`.env.prod` files. See the [deployment contract](orca-wsl-build-deploy/references/deployment-contract.md) and [security model](orca-wsl-build-deploy/references/security-model.md).

```bash
SKILL_ROOT="/absolute/path/to/orca-wsl-build-deploy"
bash "$SKILL_ROOT/scripts/wsl-bridge.sh" require
bash "$SKILL_ROOT/scripts/deliver.sh" build dev myapp
bash "$SKILL_ROOT/scripts/deliver.sh" deploy dev myapp 'myapp:TAG'
bash "$SKILL_ROOT/scripts/deliver.sh" status dev myapp
```

Docker/Compose is required; remote delivery uses SSH. Production deploy/rollback needs an explicitly requested action and target configuration. `--approve-prod` is a script guard, not proof of user authorization. Default production promotion requires a health-verified dev receipt for the same image ID. Runtime state is under `~/.local/share/skills/`. Application rollback does not revert database migrations or external side effects.

Optional Gitleaks/Trivy integrations report missing tools rather than claiming a scan passed. `FF_REQUIRE_SECURITY_SCAN=1` requires the relevant scanners. These skills install no automatic command hooks.

## Validation

Before distribution, check skill names, references, documented script paths and Python/Bash syntax. Run focused verification in the target project when using the scripts. Passing discovery or static checks is not evidence of deployment success or universal agent compatibility.

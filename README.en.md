# Team Engineering Skills

[中文说明](README.md)

Team-reusable Agent Skills for Git publishing, WSL container build/debug/deploy, toolchains, coding standards, tech-stack conventions and engineering documentation. Each skill includes its own scripts and references and can be installed independently with the [skills CLI](https://github.com/vercel-labs/skills).

This collection contains team engineering practices, not an official product or certification from an agent, framework or endpoint-security vendor.

## Skills

| Skill | Scope |
| --- | --- |
| `mv-toolchain-manager` | Detect and prepare local JDK, Maven, Gradle and Node.js; respect project version managers and wrappers |
| `mv-container-delivery` | Build on the host, image in WSL; one pipeline for local run/debug, dev/prod deploy, promote and roll back |
| `mv-git-publisher` | Prepare logical commits and push as one integral action; inspect or create GitHub PRs |
| `mv-java-backend-standards` | Project-aware Java backend conventions; Spring Boot, MyBatis-Plus and JPA guidance applied per project stack |
| `mv-tech-stack-standards` | Tech-stack selection, version baselines, dependency adoption and upgrade decisions; existing projects keep their current stack |
| `mv-engineering-doc-writer` | Write, rewrite and review PRD, HLD, LLD, RFC, API docs and production MOPs |
| `mv-skill-curator` | Distill casually shared work habits and workflows into this repo: triage, merge, split, refactor and validate |

Naming: use `mv-` plus object and responsibility word. The responsibility word follows the skill's primary responsibility, consistent with its description and body. See the [repository structure rules](mv-skill-curator/references/structure-rules.md).

Installing locally is optional: when needed, run `bash mv-skill-curator/scripts/sync-installed.sh` (add `--remote` to install from the GitHub source); the script installs all skills and removes obsolete versions, avoiding duplicate triggers. Whether to install is up to the user.

“Reusable” means across this team's projects, not a universal standard for every company or team. Skills use confirmed team conventions as their baseline and leave business-specific details in each project. Team Git rules require pulling and resolving conflicts before both committing and pushing, keeping linear history and avoiding merge commits.

## Maintenance principles

- Extract team-reusable methods, conventions and verification criteria from experience. Encode confirmed team rules directly rather than making them optional because other teams may differ. Do not copy project-specific business rules, fixed paths or credentials.
- Keep the current workflow in SKILL.md and load environment/framework details from references as needed. Update descriptions, examples, entry points and links together so obsolete instructions do not remain active.
- Report compilation, unit tests, mock integration and real-system integration separately. Static checks do not establish behavior; use scoped machine checks for recurring mechanical errors rather than accumulating reminders.

## Install

Install from this repository:

```bash
npx skills@latest add xiaoshitou1997/skills --list
npx skills@latest add xiaoshitou1997/skills
npx skills@latest add xiaoshitou1997/skills --skill mv-git-publisher -g -a claude-code
# Local checkout: list skills without installing
npx skills@latest add . --list
```

The CLI supports multiple agents; select the target with `-a`. Skills are loaded according to the selected agent's behavior. Node.js is needed for the CLI. Python utilities need Python 3 (`python3`, `python` or `py -3`, depending on the environment); shell utilities need Bash and their documented tools.

## Run bundled tools

Locate the installed skill through its loaded `SKILL.md`. `SKILL_ROOT` below is an explicitly assigned absolute path, not an agent-provided variable. Run project-oriented commands from your application repository:

```bash
SKILL_ROOT="/absolute/path/to/mv-toolchain-manager"
python3 "$SKILL_ROOT/scripts/doctor.py" --project .

SKILL_ROOT="/absolute/path/to/mv-git-publisher"
python3 "$SKILL_ROOT/scripts/stage_audit.py"
bash "$SKILL_ROOT/scripts/pr.sh" view
```

Commit language and format follow the user and repository conventions. The default in the absence of conventions is Chinese Conventional Commits. Existing staged changes are preserved and inspected before committing.

## WSL build & deploy

`mv-container-delivery` unifies local run/debug and dev/prod delivery in one pipeline: artifacts are built on the host (toolchains prepared by mv-toolchain-manager), packaged in WSL into thin runtime-only images, and deployed to the local WSL (dev, the local server) or a remote server (prod). Built-in templates cover Java executable JARs and static Node frontends; other artifact layouts use `FF_ARTIFACT` or a project-owned `Dockerfile.delivery`. Prepare `.dockerignore` and untracked `.env.dev`/`.env.prod` files. See the [deployment contract](mv-container-delivery/references/deployment-contract.md) and [security model](mv-container-delivery/references/security-model.md).

```bash
SKILL_ROOT="/absolute/path/to/mv-container-delivery"
bash "$SKILL_ROOT/scripts/wsl-bridge.sh" require
bash "$SKILL_ROOT/scripts/deliver.sh" build dev myapp
bash "$SKILL_ROOT/scripts/deliver.sh" deploy dev myapp 'myapp:TAG'
bash "$SKILL_ROOT/scripts/deliver.sh" status dev myapp
```

Docker/Compose is required; remote delivery uses SSH. Production deploy/rollback needs an explicitly requested action and target configuration. `--approve-prod` is a script guard, not proof of user authorization. Default production promotion requires a health-verified dev receipt for the same image ID. Runtime state is under `~/.local/share/skills/`. Application rollback does not revert database migrations or external side effects.

Optional Gitleaks/Trivy integrations report missing tools rather than claiming a scan passed. `FF_REQUIRE_SECURITY_SCAN=1` requires the relevant scanners. These skills install no automatic command hooks.

## Validation

Before distribution, check skill names, references, documented script paths and Python/Bash syntax. Run focused verification in the target project when using the scripts. Passing discovery or static checks is not evidence of deployment success or universal agent compatibility.

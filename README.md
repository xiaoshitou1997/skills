# Team Engineering Skills

[中文说明](README.zh-CN.md)

Team-reusable Agent Skills for development, Git publishing and Docker delivery. Each skill includes its own scripts and references and can be installed independently with the [skills CLI](https://github.com/vercel-labs/skills).

This collection contains team engineering practices, not an official product or certification from an agent, framework or endpoint-security vendor.

## Skills

| Skill | Scope |
| --- | --- |
| `toolchain-manager` | Detect and prepare local JDK, Maven, Gradle and Node.js; respect project version managers and wrappers |
| `local-development` | Start, reproduce, debug and stop local applications; run focused verification |
| `git-publisher` | Prepare logical commits, push when requested, and inspect or create GitHub PRs |
| `docker-delivery` | Container builds, Compose deployment, same-image promotion, health checks and application rollback |
| `spring-boot-standards` | Project-aware Spring Boot conventions; MyBatis-Plus guidance where applicable |
| `windows-dlp-environment` | Machine-specific Windows DLP/EDR diagnosis, file access and WSL build observations |

Renamed skills: `application-delivery` → `docker-delivery`, `java-backend-standards` → `spring-boot-standards`, `dlp-machine-env` → `windows-dlp-environment`. If an old version is already installed, remove it explicitly and install the new name to avoid duplicate triggers.

“Reusable” means across this team's projects, not a universal standard for every company or team. Except for the machine-specific `windows-dlp-environment`, skills use confirmed team conventions as their baseline and leave business-specific details in each project. Team Git rules require pulling and resolving conflicts before committing, keeping linear history and avoiding merge commits.

## Maintenance principles

- Extract team-reusable methods, conventions and verification criteria from experience. Encode confirmed team rules directly rather than making them optional because other teams may differ. Do not copy project-specific business rules, fixed paths or credentials.
- Keep the current workflow in SKILL.md and load environment/framework details from references as needed. Update descriptions, examples, entry points and links together so obsolete instructions do not remain active.
- Report compilation, unit tests, mock integration and real-system integration separately. Static checks do not establish behavior; use scoped machine checks for recurring mechanical errors rather than accumulating reminders.

## Install

Install from this repository:

```bash
npx skills@latest add xiaoshitou1997/skills --list
npx skills@latest add xiaoshitou1997/skills
npx skills@latest add xiaoshitou1997/skills --skill git-publisher -g -a claude-code
# Local checkout: list skills without installing
npx skills@latest add . --list
```

The CLI supports multiple agents; select the target with `-a`. Skills are loaded according to the selected agent's behavior. Node.js is needed for the CLI. Python utilities need Python 3 (`python3`, `python` or `py -3`, depending on the environment); shell utilities need Bash and their documented tools. The prose-only Windows environment skill requires no runtime installation by itself.

## Run bundled tools

Locate the installed skill through its loaded `SKILL.md`. `SKILL_ROOT` below is an explicitly assigned absolute path, not an agent-provided variable. Run project-oriented commands from your application repository:

```bash
SKILL_ROOT="/absolute/path/to/toolchain-manager"
python3 "$SKILL_ROOT/scripts/doctor.py" --project .

SKILL_ROOT="/absolute/path/to/git-publisher"
python3 "$SKILL_ROOT/scripts/stage_audit.py"
bash "$SKILL_ROOT/scripts/pr.sh" view
```

Commit language and format follow the user and repository conventions. The default in the absence of conventions is Chinese Conventional Commits. Existing staged changes are preserved and inspected before committing.

## Docker delivery

Built-in templates cover Java executable JARs and static Node frontends. Other architectures need project-owned Dockerfile/Compose configuration. Prepare `.dockerignore` and untracked `.env.dev`/`.env.prod` files. See the [deployment contract](docker-delivery/references/deployment-contract.md) and [security model](docker-delivery/references/security-model.md).

```bash
SKILL_ROOT="/absolute/path/to/docker-delivery"
bash "$SKILL_ROOT/scripts/deliver.sh" build dev myapp
bash "$SKILL_ROOT/scripts/deliver.sh" deploy dev myapp 'myapp:TAG'
bash "$SKILL_ROOT/scripts/deliver.sh" status dev myapp
```

Docker/Compose is required; remote delivery uses SSH. Production deploy/rollback needs an explicitly requested action and target configuration. `--approve-prod` is a script guard, not proof of user authorization. Default production promotion requires a health-verified dev receipt for the same image ID. Runtime state is under `~/.local/share/skills/`. Application rollback does not revert database migrations or external side effects.

Optional Gitleaks/Trivy integrations report missing tools rather than claiming a scan passed. `FF_REQUIRE_SECURITY_SCAN=1` requires the relevant scanners. These skills install no automatic command hooks.

## Validation

Before distribution, check skill names, references, documented script paths and Python/Bash syntax. Run focused verification in the target project when using the scripts. Passing discovery or static checks is not evidence of deployment success or universal agent compatibility.

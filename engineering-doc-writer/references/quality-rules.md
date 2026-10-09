# Engineering Document Quality Rules

## 1. Independent deliverable

The reader should understand the document without access to the chat, previous revisions, meeting history, or author intent.

Remove phrases such as:

- `根据您的要求`
- `结合之前的讨论`
- `以下是本次方案`
- `如前所述`
- `本次调整后`
- `之前的版本`

Replace them with stable system statements.

## 2. Do not fabricate completeness

Never invent:

- performance numbers or SLOs;
- capacity claims;
- interface fields or error codes;
- owners or responsible teams;
- release dates or milestones;
- product or middleware versions;
- dependencies such as Redis, Kafka, Prometheus, Grafana, ELK;
- security, availability, or compliance claims.

Use one of:

- `TBD`
- `Unknown`
- `Assumption`
- `Open Question`

## 3. Separate statement types

Treat input carefully:

| Type | Meaning | Document behavior |
|---|---|---|
| Fact | Confirmed current behavior/evidence | State directly |
| Requirement | Required future/target behavior | Express as requirement |
| Decision | Selected design/approach | Record with rationale |
| Assumption | Unverified condition required by the design | Label explicitly |
| Open Question | Missing decision/information | Keep unresolved |
| Discussion | Exploration or suggestion | Do not silently promote |

Example:

Input: `以后会不会支持三个 Region？`

Do not write: `系统支持三个 Region。`

Write: `Open Question: 是否需要扩展至三个 Region？当前输入未确认。`

## 4. Requirements versus design

Do not write technology choices as business/functional requirements unless the technology is a mandated constraint.

Bad:

`Requirement: 使用 Redis 保存状态。`

Better:

`Requirement: 跨 Region 状态最终一致。`

`Design: 使用 Redis 保存状态。`

## 5. Decisions and trade-offs

For RFC/HLD decisions, capture:

- selected option;
- why it was selected;
- rejected alternatives;
- cost, risk, compatibility impact, or operational burden.

If no option is selected, use `Decision: TBD`.

## 6. Traceability

When evidence exists, make key claims traceable to one of:

- requirement ID;
- code symbol and location;
- endpoint or schema;
- configuration key;
- log/event evidence;
- observed measurement and time window;
- formal external specification.

Do not create fake citations or source labels.

## 7. Terminology control

- Define abbreviations on first meaningful use when the audience may not know them.
- Lock one term per concept.
- Do not interchange `Session`, `Token`, `Credential`, `Cookie`, and `Auth State` without defining differences.
- Match actual code/config/API casing when supplied.

## 8. Scope control

Use `In Scope` / `Out of Scope` when boundaries are important.

Do not add adjacent themes such as OAuth, SSO, JWT, monitoring, CI/CD, audit, multi-region, caching, or message queues unless supported by requirements or design inputs.

## 9. Verifiable language

Avoid:

- `性能优异`
- `高可用`
- `安全可靠`
- `支持大规模并发`
- `显著提升`

Prefer:

- `P99 latency target: TBD.`
- `Availability target: TBD.`
- `Capacity must be verified against [known workload].`

## 10. Style

Use neutral engineering language.

Avoid:

- first/second person;
- subjective praise;
- filler paragraphs;
- meta-narration such as `本节将介绍`;
- colloquial wording;
- repeated conclusions across sections.

Each paragraph should add information.

## 11. Markdown

- Use headings in order without skipping levels.
- Prefer headings, lists, tables, code fences, links, and Mermaid.
- Do not use decorative emoji.
- Avoid bold/italic/strikethrough as the primary structure mechanism.
- Keep JSON/YAML expanded and readable.
- Keep shell commands copyable and omit shell prompt characters.
- Use Mermaid instead of ASCII architecture diagrams.

## 12. Diagram consistency

Before finalizing, verify:

- component names match prose;
- sequence order matches described flow;
- stores/protocols shown in diagrams also appear in prose;
- diagrams do not introduce unconfirmed dependencies.

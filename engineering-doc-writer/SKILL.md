---
name: engineering-doc-writer
description: >-
  Create, rewrite, review, and standardize software-engineering documents in Chinese or bilingual engineering contexts. Use for PRD, HLD/architecture design, LLD/detailed design, RFC/technical proposals, API documentation, production upgrade or deployment MOP (Method of Procedure), runbooks, troubleshooting guides, postmortems, implementation plans, README/CHANGELOG delivery sections, and similar engineering artifacts. Apply when the user wants a document that can stand alone, be reviewed, implemented, operated, or archived. Preserve source facts, separate facts/requirements/assumptions/open questions, avoid invented details, keep terminology and decisions consistent, and produce repository-friendly Markdown unless another artifact format is explicitly requested.
---

# Engineering Document Writer

Produce engineering documents as independent deliverables rather than extensions of the current chat.

## Core workflow

1. Determine the task mode:
   - Create: build a new document from requirements, notes, source files, code, or discussion.
   - Rewrite: transform an existing draft into a reviewable engineering document.
   - Review: identify defects, ambiguity, missing decisions, contradictions, unverifiable claims, and operational gaps.
2. Determine the document type from user intent. Prefer PRD, HLD, LLD, RFC, API, or MOP when applicable.
3. Classify input statements before drafting:
   - Fact: confirmed system behavior, data, code, configuration, interface, or observed result.
   - Requirement: explicitly required behavior or constraint.
   - Decision: an explicitly selected solution or trade-off.
   - Assumption: necessary but unverified condition.
   - Open Question: unresolved decision or missing input.
   - Discussion: exploratory content that should not silently become a requirement.
4. Load only the relevant structure from `references/document-types.md`. For production upgrade/deployment procedures, also load `references/mop-guide.md`.
5. Apply `references/quality-rules.md` while drafting.
6. Run the final checks in `references/self-check.md` before returning the document.

Do not ask for missing details if a useful draft can be produced safely. Use `TBD`, `Assumption`, `Open Question`, or an explicit placeholder instead of inventing values.

## Source fidelity

When source files, screenshots, tickets, meeting notes, code, or user-provided text are the basis of the document:

- Preserve what the sources actually support.
- Preserve established terminology, identifiers, endpoint names, configuration keys, version labels, and responsibility boundaries.
- Do not silently correct, reconcile, or expand unsupported points.
- If external knowledge or inference is added, distinguish it from source-derived content.
- Do not expose source filenames, chat history, or drafting process in the final document unless the source itself is a formal reference that should appear in `References`.

## Content rules

- Make the document independently understandable without access to the conversation.
- Use objective engineering language.
- Keep one concept under one stable term throughout the document.
- Separate requirements from implementation choices.
- Separate decisions from alternatives and unresolved questions.
- Make non-trivial claims traceable to code, configuration, interfaces, requirements, data, logs, or formal references when such evidence is available.
- Prefer explicit unknowns over plausible-sounding completion.
- Include trade-offs when a design decision has meaningful cost or risk.
- Include `In Scope` and `Out of Scope` when scope expansion is plausible.
- Do not add empty sections merely to make the document look complete.

## Default writing style

Use Chinese engineering prose unless the user requests another language.

- Avoid first- and second-person wording such as `我们`、`你`、`您`.
- Avoid chat phrases such as `根据您的要求`、`以下是`、`结合之前讨论`、`本次调整`.
- Avoid unsupported praise such as `高性能`、`高可用`、`先进`、`优雅`.
- Avoid colloquial wording such as `搞`、`弄`、`东西`、`到时候`、`回头`、`搞定`.
- Keep Chinese and English/number boundaries readable, for example `TLS 1.3`、`P99 18 ms`、`Redis 集群`.
- Prefer plain Markdown. Avoid decorative emoji, excessive emphasis, and ornamental separators.
- Use Mermaid for architecture, flow, and sequence diagrams when a diagram materially improves understanding.

## Document-type behavior

### PRD

Focus on problem, target users/actors, goals, scope, requirements, acceptance criteria, dependencies, and open questions. Do not prematurely turn implementation ideas into requirements.

### HLD

Focus on system context, architecture, components, boundaries, interfaces, data flow, deployment topology, major non-functional constraints, failure domains, and key trade-offs. Keep implementation details at a level appropriate for architecture review.

### LLD

Focus on module/class/component behavior, detailed flows, data models, interfaces, state transitions, validation, error handling, concurrency/idempotency, configuration, observability, and testable implementation details.

### RFC

Make the decision process explicit. Include the problem, goals/non-goals, proposal, alternatives considered, rationale, consequences/trade-offs, compatibility/migration concerns, risks, and unresolved questions. If no decision has been made, write `Decision: TBD`.

### API documentation

Describe contract behavior precisely: purpose, endpoint or RPC name, method, path, authentication, request fields, response fields, status/error codes, validation rules, idempotency, examples, and compatibility/versioning when supported by the input. Never invent request fields or error codes.

### MOP

Treat an upgrade/deployment MOP as an executable production procedure, not a generic guide. Include preconditions, change scope, prerequisites, backup, step-by-step commands/actions, checkpoints, success criteria, rollback triggers, rollback procedure, post-change validation, and ownership only when confirmed. Load `references/mop-guide.md`.

## Rewrite behavior

When rewriting an existing document:

- Preserve confirmed meaning unless the user requests a design change.
- Remove conversation traces, unsupported assumptions, duplicated sections, terminology drift, and formalistic filler.
- Resolve obvious structural defects without changing facts.
- Do not emit a change log unless requested.
- If a contradiction cannot be resolved from the material, retain both sides and mark the conflict as an `Open Question`.

## Review behavior

When reviewing rather than rewriting, classify findings by impact:

- Critical: could cause wrong implementation, unsafe production execution, incompatible API behavior, data loss, or unrecoverable change.
- Major: missing decision, contradiction, ambiguous ownership/boundary, unverifiable key claim, incomplete rollback or failure handling.
- Minor: terminology, formatting, wording, local clarity, or maintainability issues.

For each finding, state the problem, why it matters, and a concrete correction. Do not invent missing project facts to demonstrate a fix.

## Artifact composition

If the user explicitly requests DOCX, PDF, slides, or another rendered artifact, apply this skill to the content and structure, then use the appropriate artifact-generation capability for the file format.

## References

Read only what the current task needs:

- `references/document-types.md`: structures and section expectations for PRD, HLD, LLD, RFC, API, MOP, and related documents.
- `references/quality-rules.md`: anti-hallucination, traceability, terminology, style, and Markdown rules.
- `references/mop-guide.md`: detailed production MOP requirements, checkpoints, rollback, and validation rules.
- `references/self-check.md`: final quality gate before delivery.

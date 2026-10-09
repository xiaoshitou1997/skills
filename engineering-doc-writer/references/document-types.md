# Document Type Structures

Use these as default structures, not mandatory empty templates. Omit sections that add no information. Add sections when the domain requires them.

## PRD

```markdown
# [Product / Feature Name]

## 1. Background
## 2. Problem Statement
## 3. Goals
## 4. Non-Goals
## 5. Users and Actors
## 6. Scope
### 6.1 In Scope
### 6.2 Out of Scope
## 7. Requirements
## 8. User / Business Flow
## 9. Acceptance Criteria
## 10. Dependencies and Constraints
## 11. Risks
## 12. Open Questions
```

PRD rules:

- State the problem before the solution.
- Express requirements as observable behavior.
- Keep technology choices out of requirements unless they are themselves constraints.
- Use requirement IDs such as `REQ-001` only when traceability materially helps review or implementation.

## HLD

```markdown
# [System / Feature] High-Level Design

## 1. Overview
## 2. Goals and Non-Goals
## 3. System Context
## 4. Architecture
## 5. Component Responsibilities
## 6. Key Flows
## 7. External Interfaces
## 8. Data and State
## 9. Deployment Topology
## 10. Non-Functional Constraints
## 11. Failure Handling
## 12. Security Considerations
## 13. Observability
## 14. Trade-offs and Alternatives
## 15. Risks and Open Questions
```

HLD rules:

- Define boundaries and responsibilities before class/module detail.
- Use architecture and sequence diagrams when interactions are not obvious from prose.
- Capture failure domains, external dependencies, and major capacity assumptions.

## LLD

```markdown
# [Module / Feature] Low-Level Design

## 1. Overview
## 2. Scope
## 3. Module Structure
## 4. Detailed Flow
## 5. Interface Definitions
## 6. Data Model
## 7. State Model
## 8. Validation Rules
## 9. Error Handling
## 10. Concurrency, Idempotency, and Retry
## 11. Configuration
## 12. Logging, Metrics, and Tracing
## 13. Security Controls
## 14. Test Design
## 15. Deployment / Compatibility Notes
## 16. Open Questions
```

LLD rules:

- Make implementation behavior testable.
- Keep names aligned with actual code, schema, API, and configuration where provided.
- Document edge cases and error paths, not only the happy path.

## RFC / Technical Proposal

```markdown
# RFC: [Title]

## Abstract
## 1. Context and Problem
## 2. Goals
## 3. Non-Goals
## 4. Constraints
## 5. Proposal
## 6. Detailed Design
## 7. Compatibility and Migration
## 8. Alternatives Considered
## 9. Decision
## 10. Rationale
## 11. Consequences and Trade-offs
## 12. Risks
## 13. Rollout / Rollback
## 14. Open Questions
```

RFC rules:

- A design RFC must converge toward a decision.
- If the decision is unresolved, write `Decision: TBD` and list blocking questions.
- Do not present multiple options as if choosing among them were outside the document's purpose.

## API Documentation

```markdown
# [API Name]

## 1. Overview
## 2. Endpoint / RPC
## 3. Authentication and Authorization
## 4. Request
### 4.1 Headers / Metadata
### 4.2 Path / Query Parameters
### 4.3 Body / Message Schema
## 5. Response
### 5.1 Success Response
### 5.2 Error Response
## 6. Validation Rules
## 7. Idempotency and Retry
## 8. Examples
## 9. Compatibility and Versioning
## 10. Operational Notes
```

API rules:

- Use tables for fields: name, type, required, constraints, description.
- Match exact names and casing from source specifications or code.
- Do not invent fields, default values, error codes, or authentication methods.
- For asynchronous APIs, document callback/event correlation and retry behavior if known.

## Upgrade / Deployment MOP

```markdown
# [System] [Version] Upgrade MOP

## 1. Change Overview
## 2. Scope and Impact
## 3. Preconditions
## 4. Required Access and Artifacts
## 5. Backup and Recovery Preparation
## 6. Execution Procedure
## 7. Checkpoints and Verification
## 8. Rollback Triggers
## 9. Rollback Procedure
## 10. Post-Change Validation
## 11. Known Risks
## 12. Contacts / Owners
```

MOP rules:

- Load `mop-guide.md` before drafting.
- Keep commands copyable and ordered.
- Put validation immediately after risky or irreversible steps when possible.
- Do not claim a rollback is available unless the rollback path is actually defined.

## Runbook

Use sections such as purpose, trigger/alert, diagnosis, decision tree, remediation, verification, escalation, and recovery. Separate routine operations from emergency actions.

## Postmortem

Use sections such as summary, impact, timeline, detection, root cause, contributing factors, response, recovery, lessons, corrective actions, and evidence. Do not assign motives or blame without evidence.

## Implementation Plan

Use sections such as objective, scope, work breakdown, dependencies, milestones, migration, test plan, rollout, rollback, risks, and open questions. Do not fabricate dates or owners.

## Filename conventions

Prefer lowercase names with hyphens:

- `prd-<feature>.md`
- `hld-<system>.md`
- `lld-<module>.md`
- `rfc-<topic>.md`
- `api-<service>.md`
- `mop-<system>-<version>.md`

Keep one canonical document instead of `final-v2-latest` style suffixes.

# Final Quality Gate

Run this check before delivery.

## Critical

- No invented metrics, fields, versions, owners, dates, dependencies, commands, thresholds, or capabilities.
- Requirements, decisions, assumptions, and open questions are not conflated.
- No contradiction between prose, tables, and diagrams.
- No API field, status code, or behavior is stated without support from the input/source.
- For MOP, rollback covers every materially changed state or explicitly states the irreversible gap.
- For MOP, risky steps have checkpoints and post-change verification is defined.

## Major

- The document has one clear purpose and logical through-line.
- Scope boundaries are explicit where needed.
- Terminology is consistent from first use to last use.
- RFC/HLD trade-offs are present when a real decision is made.
- LLD covers error paths, validation, concurrency/idempotency/retry when relevant.
- API documentation distinguishes request, response, validation, error, and compatibility behavior.
- Unknowns are labeled rather than filled with plausible defaults.

## Style and maintainability

- No chat-history phrases or drafting meta-commentary.
- No source-material leakage unless listed as a formal reference.
- No first/second-person wording in the deliverable unless the user explicitly wants instructional prose.
- No filler sections or duplicated conclusions.
- Heading levels are valid.
- Chinese punctuation and Chinese/English spacing are consistent.
- Code/config/commands are copyable.
- Mermaid diagrams match prose and do not introduce new facts.

## Final test

Ask: could a reviewer, developer, tester, or operator use this document correctly without reading the conversation that produced it?

If not, revise before returning it.

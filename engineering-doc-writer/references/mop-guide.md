# Production Upgrade / Deployment MOP Guide

A MOP (Method of Procedure) is an executable production change procedure. Treat it as an operational control document, not a descriptive upgrade article.

## 1. Minimum information model

Capture the following when known:

- target system/service;
- source version and target version;
- affected environment/region/site;
- change window;
- expected service impact;
- deployment package/checksum/location;
- required accounts/permissions;
- configuration or database changes;
- backup method;
- rollback method;
- verification criteria;
- confirmed owner/contact.

If any critical item is unknown, mark it `TBD` rather than inventing it.

## 2. Procedure properties

Every execution step should be:

- ordered;
- atomic enough to execute and verify;
- explicit about host/component when multiple targets exist;
- explicit about commands, files, parameters, and expected results when provided;
- followed by a checkpoint when failure would materially increase recovery cost.

Avoid vague steps such as `确认系统正常` or `执行升级操作` without defining what to check or execute.

## 3. Recommended step table

For operational changes, prefer a table when it improves execution clarity:

| Step | Target | Action / Command | Expected Result | Failure Action |
|---|---|---|---|---|
| 1 | [host/service] | [action] | [observable result] | [stop/rollback/escalate] |

Do not fabricate commands. If the command is unknown, write `Command: TBD`.

## 4. Pre-change checks

Check only items relevant to the supplied system, for example:

- service status;
- active/standby role;
- current version;
- disk/memory/CPU headroom;
- database health;
- replication status;
- current traffic/alarms;
- package integrity;
- backup completion;
- change dependencies.

Do not mechanically include every check for every system.

## 5. Backup and recovery preparation

Define:

- what is backed up;
- backup location;
- backup command/process;
- restore procedure;
- validation that the backup can be used.

Configuration copy alone is not a complete rollback plan if the change also modifies database schema, data, or external dependencies.

## 6. Checkpoints

Place checkpoints after meaningful risk transitions, such as:

- stopping traffic or service;
- database DDL/DML;
- configuration replacement;
- binary/package deployment;
- restart;
- traffic restoration.

A checkpoint should define an observable pass condition.

## 7. Rollback triggers

Use explicit triggers when known, such as:

- service cannot start;
- health check fails for a defined period;
- critical API error rate exceeds a defined threshold;
- data migration validation fails;
- compatibility check fails;
- agreed business verification fails.

If thresholds are unknown, do not invent numbers. State the condition qualitatively and mark threshold values `TBD`.

## 8. Rollback procedure

Rollback must be executable and in a safe order. Cover all changed state:

- binaries/packages;
- configuration;
- database schema/data;
- traffic routing;
- caches/state if relevant;
- dependent-system changes if applicable.

State irreversibility explicitly when rollback is not technically available.

## 9. Post-change validation

Validate at multiple levels when relevant:

- process/service health;
- component/API health;
- key business flow;
- database state;
- monitoring/alarms/logs;
- external integration;
- version confirmation;
- traffic restoration.

`服务启动成功` alone is not sufficient evidence that an upgrade succeeded.

## 10. MOP versus related documents

- Upgrade Guide: explains how to upgrade in general.
- MOP: controls a concrete production execution procedure.
- Deployment Guide: covers installation/deployment patterns, sometimes broader than one change.
- Rollback Plan: focuses only on recovery.
- Runbook: covers recurring operational procedures.
- Release Notes: records what changed in the release.

When the user says `升级文档` and the content is intended for production execution with ordered actions, checks, and rollback, default to MOP.

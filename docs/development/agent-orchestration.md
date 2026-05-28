# Agent Orchestration

This document defines how KarstLab uses Codex and Claude Code together without creating conflicting changes or unclear ownership.

## Operating Model

Codex is the repository owner. It implements changes, edits files, runs tests, integrates branches, and produces final verification evidence.

Claude Code is the architecture and review partner. It plans complex work, reviews diffs, challenges design decisions, and produces handoff prompts for Codex.

Use sequential handoffs for shared or risky work. Use parallel work only when file ownership is clearly separated.

## Default Workflow

1. Claude Code plans the task.
2. Codex implements the task.
3. Claude Code reviews the diff.
4. Codex fixes review findings.
5. Codex runs validation and records the checkpoint.

## Agent Roles

| Role | Primary Agent | Use For |
|---|---|---|
| Architecture planning | Claude Code `opusplan` or `opus` | Pipeline DAG, packaging strategy, module boundaries, risk analysis |
| Implementation | Codex | Code edits, tests, integration, local verification |
| Parallel low-risk work | Claude Code `sonnet` | Land profile JSON, documentation, simple tests, UI copy |
| Final integration | Codex | Merge-ready state, full test run, release evidence |
| PR-style review | Claude Code `opus` or Codex | Bugs, architecture drift, missing tests, regressions |

## Work Package Format

Every task should be written as a small ticket:

```markdown
Task: <short title>

Context:
- Relevant docs:
- Existing modules:
- Constraints:

Scope:
- In:
- Out:

Acceptance:
- Observable result:
- Tests/checks:
- Files expected:

Ownership:
- Agent:
- Files/directories:
```

## Sequential Prompt Templates

### Prompt 1: Claude Code Planning

```text
Analyze this task and produce an implementation plan.
Do not edit files.

Return:
1. modules/files to touch
2. public interfaces and data models
3. tests to write
4. risks and tradeoffs
5. exact handoff prompt for Codex

Task:
<paste task>
```

### Prompt 2: Codex Implementation

```text
Implement this plan in the repo.
Keep scope strict.
Prefer tests first where practical.
Run relevant validation.
Report changed files, validation results, and open risks.

Plan:
<paste Claude Code plan>
```

### Prompt 3: Claude Code Review

```text
Review this diff as a PR.
Focus on bugs, architecture drift, missing tests, and release risk.
Return findings first, ordered by severity, with file/line references where possible.
Do not rewrite the implementation unless asked.

Diff/context:
<paste diff or summary>
```

### Prompt 4: Codex Review Fixes

```text
Address these review findings.
Touch only relevant files.
Run validation again.
Report each finding as fixed, deferred, or not applicable.

Findings:
<paste review>
```

## Parallel Work Rules

Parallel work is allowed only when each agent owns separate files.

Safe examples:

| Track | Agent | Files |
|---|---|---|
| Raster/CRS/VRT | Codex | `src/karstlab/data/*`, `tests/test_raster_io.py`, `tests/test_crs.py` |
| Land profiles | Claude Code Sonnet | `src/karstlab/resources/regions/*.json` |
| Report template | Claude Code Sonnet | `src/karstlab/resources/templates/report.html.j2` |
| GUI shell | Codex | `src/karstlab/presentation/*` |
| POI docs/tests | Claude Code Sonnet | `tests/test_poi.py`, docs only |

Do not run parallel edits on:

- `pyproject.toml`
- shared Pydantic schemas
- `pipeline_dag.py`
- project file schema
- package initialization files
- release/build scripts

## Shared Contracts To Freeze Early

These contracts must be created before large parallel implementation starts:

- `AnalysisParams`
- `ProjectFile`
- `LandProfile`
- `DepressionResult`
- `PipelineResult`
- project directory layout: `input/`, `output/`, `export/`, `cache/`, `logs/`
- canonical output filenames
- pipeline step IDs

## Integration Discipline

- One agent integrates to the main working tree at a time.
- Keep tasks small enough to validate in one session.
- Every implementation handoff must include changed files and validation evidence.
- Network-dependent tests must be marked and skipped by default.
- If agents disagree, Codex records the decision in `get-shit-done/project.md` and implements the selected path.


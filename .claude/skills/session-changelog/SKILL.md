---
name: session-changelog
description: Write the end-of-session changelog folder (5 files, zh/en/ko) and sync the milestone checkboxes in both weekly plans. Use at the end of a working session, or when asked to "record this session", "write the changelog", or "정산".
disable-model-invocation: true
---

Produce the per-session record this project requires. Two deliverables — do both.

## 1. `changelog/<M_D>/` — five files

`<M_D>` is month_day, no year, no zero padding (`7_29`, `8_19`). Use today's date. If the folder
already exists, extend the existing files rather than overwriting them.

| File | Language | Content |
|---|---|---|
| `CHANGELOG_<M_D>.md` | Chinese | What was delivered, with mermaid diagram(s) |
| `CHANGELOG_en_<M_D>.md` | English | Same log, framed as a progress report |
| `presentation_<M_D>.md` | Chinese | Presentation material |
| `presentation_en_<M_D>.md` | English | Same |
| `presentation_ko_<M_D>.md` | Korean | Same |

Read the most recent existing folder under `changelog/` first and match its structure, heading depth,
and tone. The English file is a *reframing* for a progress report, not a literal translation.

Content rules:
- Say what actually changed, with file paths. Ground every claim in the diff (`git diff`, `git status`)
  and in what was run this session — do not describe intended work as done.
- If tests were run, state the result and the command. If they were not run, say so.
- Include at least one mermaid diagram in the changelogs when the session touched architecture, the
  DSL pipeline, or the verification loop.
- Note which research question (RQ1–RQ4) and milestone (M1–M10) the work belongs to.

## 2. Sync both weekly plans

Tick the milestone checkboxes in **both** `docs/weekly_plan.md` (Chinese) and `docs/weekly_plan_en.md`
(English). They must stay in sync — a checkbox ticked in one and not the other is a bug.

Only tick an item that is genuinely finished and verified. Partial work gets a note, not a checkmark.

## Finally

Report the folder path, the five filenames, and which checkboxes you ticked. Do not commit unless
asked.

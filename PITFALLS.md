# Mistakes in earlier audits and benchmark reports, and how this audit avoids each

Each row names a mistake that is documented in a public source, and the rule here that prevents it. "Enforced by" says whether the rule is checked by code or depends on the auditor following the protocol. Rules marked (A1) were added by the 2026-10-13 amendment in `PLAN.md`.

## Who audits and how it is documented

| Mistake | Where it is documented | Rule here | Enforced by |
|---|---|---|---|
| The audit was done by a language model, with unspecified "human review" | LoCoMo audit report: "Auditor: Claude Opus 4.6 (Anthropic), with human review" ([report](https://github.com/dial481/locomo-audit/blob/main/AUDIT_REPORT.md)) | A person writes the answer and makes every call. A model pass is run separately and reported as a model pass | Protocol; the tool records every human answer with a timestamp before gold is shown |
| Number of annotators, time spent and review process not stated | Same report; the LongMemEval paper also reports no inter-annotator agreement ([paper](https://arxiv.org/pdf/2410.10813)) | Every release states: one annotator, who it was, hours spent, the tool used, and the agreement statistics that exist. Missing checks are stated as missing | Release checklist (A1) |
| The auditor sells a competing product | Penfield Labs, Zep, the author of arXiv 2609.38021 | Interest is disclosed in `PLAN.md` and `README.md`. No score for any system of the auditor's is reported in this repository | Protocol |

## Which questions get looked at

| Mistake | Where it is documented | Rule here | Enforced by |
|---|---|---|---|
| Only the questions the auditor's own system failed were inspected, so the error list is conditioned on one system | arXiv 2609.38021 says its dossier "was built from the grok pair's failures" and that other failures "were not audited for gold defects" ([paper](https://arxiv.org/abs/2609.38021)) | Questions are chosen by a seeded random sample, then all 500. No system output is consulted when choosing or labelling | `scripts/sample.py`; `sample_v01.json` |
| A gold error is reported in order to claim a perfect score on the remaining questions | LongMemEval issues [#37](https://github.com/xiaowu0162/LongMemEval/issues/37), [#40](https://github.com/xiaowu0162/LongMemEval/issues/40), [#41](https://github.com/xiaowu0162/LongMemEval/issues/41) | No "accuracy on the remaining valid questions" figure is ever computed or reported here | Protocol |
| A whole category was left out | The LoCoMo audit excluded all 446 adversarial questions | Abstention questions are a stratum of the sample and are covered in the full release | `scripts/sample.py` |
| Other people's findings were counted as one's own | General risk; 370a8ff4 has been reported four separate times on the tracker | Publicly reported IDs sit in their own stratum, are verified separately and are excluded from the sample rate | `prior_reports.csv`; `scripts/sample.py` |

## How a call is made

| Mistake | Where it is documented | Rule here | Enforced by |
|---|---|---|---|
| The gold answer was seen before the auditor formed an answer | arXiv 2609.38021 states its dossier "records per-row inspection of gold answers during development" | The answer is locked before gold is revealed; the server does not send gold before the lock | Annotation tool |
| A defect was published as strict, then downgraded | arXiv 2609.38021 section 6.3: one row "published as strict; reclassified"; issue #40: an error reported and withdrawn in the same thread | A call is **definite** only if it passes the definite checklist below. Everything else is **ambiguous** and stays out of the headline rate (A1) | Release check script (A1) |
| Errors that depend on how a phrase is read were presented as errors | Seven of the eight dossier rows are "boundary-semantic (defensible readings on both sides)" | Any call that depends on reading a relative date ("last Thursday"), a window boundary, or plan versus completed action is ambiguous unless every reasonable reading contradicts the gold (A1) | Definite checklist |
| No second look before publishing | Issue #40, withdrawn the same day | Every definite call is re-examined on a later calendar day before any release, and the re-examination is recorded as a new label event (A1) | Release check script (A1) |
| No one else checked the calls | arXiv 2609.38021: "A third-party human adjudicator has not checked this classification" | Delayed re-annotation and a volunteer subset in v1.0. For v0.1, which has neither, this is stated in the release, and every item is published with its quote so a reader can check it | Protocol; release checklist |

## What data the claim is about

| Mistake | Where it is documented | Rule here | Enforced by |
|---|---|---|---|
| Errors reported against a superseded version of the data | Issues [#11](https://github.com/xiaowu0162/LongMemEval/issues/11) and [#12](https://github.com/xiaowu0162/LongMemEval/issues/12) predate the 2025-09-19 cleaned release | Every claim names the dataset revision and file hash. For each prior report, the verification records whether the problem is still present at the pinned revision (A1) | `counts.json`; the tool refuses to start on a different file hash |
| Results on the evidence-only file presented as results on the full benchmark | arXiv 2609.38021 notes a public claim whose runner used `longmemeval_oracle.json` | This audit reads the evidence-only file. Its claims say "given the labelled evidence sessions". It does not claim to find errors caused by filler sessions in the S or M files, which is a stated limitation (A1) | Release checklist |
| Broken items found but no list or counts published | Mastra's workflow note says there "appear to be many broken question/answer pairs" without publishing them | The full item ledger is released, including every OK item | Protocol |

## How numbers are reported

| Mistake | Where it is documented | Rule here | Enforced by |
|---|---|---|---|
| Averages over categories quoted as if they were raw accuracy | arXiv 2609.38021 section 2 on two widely quoted percentages | Every rate is given as a raw count over a stated denominator, with a Wilson interval. No category-averaged figure is used as a headline (A1) | Release checklist |
| A sample result stated as a fact about the whole benchmark | General risk for a 120-item first release | v0.1 reports the sample rate and interval and says it is a sample. No ceiling for the benchmark is stated before all 500 are done (A1) | Release checklist |
| Numbers typed by hand drift from the data | The auditor's own earlier paper needed a prose audit and had double-rounding errors | Every number in a release is produced by a script from `annotations/*.jsonl` and rounded once from the raw value (A1) | Release check script (A1) |
| Judge leniency tested with one judge and undocumented wrong answers | The LoCoMo audit post does not state which model wrote its wrong answers and used one judge | Judges are named with versions. Wrong answers are produced by a documented, scripted rule (for example a different entity or value of the same type taken from the same evidence), and the rule and every candidate are released (A1) | Protocol |
| A different judge model quoted against official-judge scores | arXiv 2609.38021 section 2 | Any judge other than `gpt-4o-2024-08-06` is labelled as answering a different question | Protocol |

## After the findings

| Mistake | Where it is documented | Rule here | Enforced by |
|---|---|---|---|
| The same error filed again as a new issue | 370a8ff4: issues #19, #26, #40, #41 | Before anything is sent to the owner, each item is checked against `prior_reports.csv` and the live tracker; items already reported are referenced by their existing issue number | Protocol; `GATE.md` re-run |
| Corrections released under a licence users cannot adopt | The LoCoMo audit is CC BY-NC 4.0 because LoCoMo is | Corrected fields are released as an MIT overlay keyed by `question_id`; the dataset itself is not redistributed | `README.md` |
| Fixes promised and not delivered left users unsure which key is right | Issues #19, #21, #22: "will fix in a future version", still open | The overlay is versioned and usable without waiting for the owner | Protocol |

## Definite checklist (A1)

A non-OK call may be tiered **definite** only if all of these hold. Otherwise it is **ambiguous**.

1. The supporting quote is copied verbatim from an evidence turn and the turn is identified.
2. The contradiction does not depend on choosing one of several reasonable readings of a phrase. If a reasonable reader could reach the gold answer, the call is ambiguous.
3. For date or count calls, the arithmetic is written out in the justification (dates, the difference, the unit).
4. The call was re-examined on a later calendar day and confirmed.
5. It is not explained by information that could only be in a session outside the labelled evidence.

## Release checklist (A1)

Before any release:

1. `scripts/release_check.py` passes: every definite call has a quote and a confirming label event from a later day; every number in the release notes matches the script output.
2. The release notes state the annotator count, hours, what agreement checks exist and which do not, the dataset revision, and the evidence-only limitation.
3. Rates are raw counts with denominators and Wilson intervals; a sample is called a sample.
4. The prior-work search in `GATE.md` has been re-run and its date updated.
5. Every item going to the owner has been checked against the live issue tracker.

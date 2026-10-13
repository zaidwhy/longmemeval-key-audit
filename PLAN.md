# PLAN - LongMemEval answer-key audit (preregistration)

STATUS: FROZEN 2026-10-13 at git tag `prereg-v1`. No gold answer in the sample had been read when this was frozen. Any later change is a dated entry in the change log.

## Question

How many of the 500 LongMemEval questions have a gold answer or an evidence label that the benchmark's own evidence sessions do not support?

## Data

- `longmemeval_oracle.json` from `xiaowu0162/longmemeval-cleaned`, revision `98d7416c24c778c2fee6e6f3006e7a073259d48f`, SHA-256 `821a2034d219ab45846873dd14c14f12cfe7776e73527a483f9dac095d38620c` (see `counts.json`).
- The oracle file holds only the evidence sessions. Errors caused by filler sessions in the S and M files are out of scope for the key audit and are recorded only when a prior report names them.

## Procedure

For each question: read the question, the question date and every evidence session; write the answer the evidence supports; only then read the gold answer and compare. Record the supporting quote and a one-line justification for every item, error or not.

## Taxonomy

| Code | Meaning |
|---|---|
| OK | Gold answer is the only answer the evidence supports |
| WRONG_GOLD | Evidence supports a different answer |
| MULTIPLE | Evidence supports more than one answer and the gold names one |
| UNSUPPORTED | Evidence does not determine an answer (non-abstention questions) |
| ABSTENTION_ANSWERABLE | Abstention question whose evidence does answer it |
| UNCLEAR_QUESTION | Question is ambiguous or has a false premise |
| EVIDENCE_LABEL | Gold answer is right but `answer_session_ids` or `has_answer` is incomplete or wrong |

Every non-OK call is tiered **definite** or **ambiguous**. The headline rate counts definite score-affecting calls only (all codes except EVIDENCE_LABEL), so it is a lower bound. EVIDENCE_LABEL is reported separately because it affects retrieval metrics, not answer scoring.

## Strata and first release (v0.1)

- **Prior-reported stratum:** the question IDs in `prior_reports.csv`. Analysed as verification of other people's reports. Never counted as findings of this audit and never included in the sample rate.
- **Sample:** 120 questions drawn by `scripts/sample.py`, seed 20261013, proportional across the six question types plus an abstention stratum, from the questions not in the prior-reported stratum. The sample was re-drawn once before the freeze, with the same seed, after the eight dossier IDs from arXiv 2609.38021 and one second-hand report were added to `prior_reports.csv` (21 prior-reported IDs, pool of 479). The frozen list is `sample_v01.json`.
- **Reported:** definite error rate with a 95% Wilson interval, per-type counts, and the full item ledger.

## Full release (v1.0)

- All 500 questions.
- **Intra-annotator agreement:** a seeded random 15% re-annotated at least 14 days after first annotation without sight of the first labels; Cohen's kappa on OK versus non-OK with a bootstrap interval.
- **Second annotator:** one volunteer annotates 50 to 100 seeded items; same statistics. If no volunteer is found, this is stated.
- **Model pass:** one open-weight model applies the same procedure to all 500. Reported as a model pass, not as an annotator, with its agreement against the human labels.

## Judge test (secondary)

On a seeded sample of questions with OK gold answers, score three kinds of candidate answer with the official per-type judge prompts: the gold answer (false-reject control), a wrong but topically adjacent answer (false accept), and an unrelated answer (negative control). Report false-accept and false-reject rates with Wilson intervals per judge model. Judges used are named with their versions; any judge other than `gpt-4o-2024-08-06` answers a different question from the official protocol and is labelled so.

## Predictions (written before data)

- Definite score-affecting error rate in the sample: 3% (Zaid's prediction, entered 2026-10-13).
- Temporal-reasoning and multi-session questions carry more errors than single-session ones.
- Judge false-accept rate is low (prior small probes report about 1%). A clean result is reported as a clean result.

## Prior exposure (disclosed)

- The reports in `prior_reports.csv`, including the gold answers quoted in those issues.
- The headline figures of the LoCoMo audit (99 of 1,540; 62.81%) and its report.
- Earlier work on LoCoMo category 1 for the TCMF paper. LongMemEval data was never on this machine before 2026-10-13.
- `counts.json` and `sample_v01.json` were produced before the freeze from question IDs, types and evidence flags only.

## Interest

No commercial memory product. The auditor builds research memory systems and has a paper under review that reports a LoCoMo retrieval result.

## Pre-emption rule

The prior-work search in `GATE.md` is re-run before each release. If a full, non-vendor re-annotation of LongMemEval appears first, this project becomes an agreement study against it and is released as a short report.

## Disclosure

When v0.1 is public, the benchmark owner is sent the item ledger for the non-OK items. Corrected fields are released as an overlay keyed by `question_id`, MIT licensed.

## Budget

Zero paid calls. Annotation needs no model. Model calls are cached and resumable.

## Schedule

- 19 Oct - 8 Nov 2026: first release (v0.1). The prior-reported stratum and the 120-question sample, reading only.
- 9 Nov - 5 Dec: no audit work. Semester exams run 16 to 30 Nov and practicals until 5 Dec.
- 5 - 15 Dec: no audit work. Paper revision and submission for another project.
- 16 Dec 2026 - 10 Jan 2027: remaining 380 questions, delayed re-annotation, second annotator, model pass, judge test.
- 11 - 31 Jan 2027: full release (v1.0) and write-up.

If v0.1 slips past 8 Nov it resumes on 16 Dec; it is not worked on during the exam period.

## Amendment A1 (2026-10-13, before any annotation)

Added after reviewing the documented mistakes of earlier audits; the full mapping is in `PITFALLS.md`. No gold answer in the sample had been read when this was added. A1 tightens the protocol and removes nothing.

1. **Definite tier.** A non-OK call is definite only if it passes the definite checklist in `PITFALLS.md` (verbatim quote, no dependence on one of several reasonable readings, arithmetic written out, confirmed on a later calendar day, not explained by sessions outside the labelled evidence). Otherwise it is ambiguous.
2. **Second look.** Every definite call is re-examined on a later calendar day before a release, recorded as a new label event.
3. **Scope wording.** Claims are about the gold answer given the labelled evidence sessions at the pinned revision. Errors caused by filler sessions in the S and M files are not detected by this audit, and each release says so.
4. **Prior reports.** For each prior-reported item the verification also records whether the problem is present at the pinned revision.
5. **Reporting.** Raw counts with denominators and Wilson intervals; no category-averaged headline; a sample is called a sample and no benchmark-wide ceiling is stated before all 500 are done; no score for any system of the auditor's; no accuracy "on the remaining valid questions".
6. **Numbers.** Every released number is produced by a script from `annotations/*.jsonl`.
7. **Judge test.** Wrong candidate answers are produced by a documented, scripted rule, and the rule and all candidates are released.
8. **Release notes** state the annotator count, hours, which agreement checks exist and which do not.

## Amendment A2 (2026-10-13, before any annotation)

Changes the reading procedure. When it was added, the annotation file held one session-start event and no locked answer, so no gold answer had been seen.

**Reason.** Reading load was measured from the data (word counts only, no answers): the 141 first-release items hold about 650,000 words of evidence, of which about 75,000 are user turns. Reading every word is about 43 hours for the first release and about 141 hours for all 500, at 250 words a minute. That is not feasible for one annotator.

**New procedure.**
1. User turns are read in full for every question.
2. Assistant turns are shown collapsed and are searchable. For questions of type `single-session-assistant`, which ask about what the assistant said, all turns are shown and read in full.
3. Before any non-OK label, the assistant turns are searched or read for anything that changes the call. The tool requires this to be confirmed and records it.
4. The tool records, per item, how many assistant turns were opened and how many searches were run, and these counts are released with the ledger.

**Consequence, stated in every release.** An error that is visible only in an assistant turn can be missed on an item labelled OK. The reported error rate was already defined as a lower bound; A2 makes that bound looser, not invalid. Non-OK calls are not weakened, because rule 3 applies to all of them.

## Change log

- 2026-10-13: draft written.
- 2026-10-13: prior reports extended to 21 question IDs, sample re-drawn with the same seed, prediction entered, schedule added, frozen at tag `prereg-v1`.
- 2026-10-13: Amendment A1 added (see above and `PITFALLS.md`), before any annotation. Annotation may begin before 19 Oct; the schedule dates are latest starts, not earliest.
- 2026-10-13: Amendment A2 added (reading procedure: user turns in full, assistant turns collapsed and searchable), before any answer was locked.

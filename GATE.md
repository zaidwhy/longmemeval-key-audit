# Novelty and scope gate

Checked 2026-10-13. Re-run before every release.

**Novelty:** no full answer-key audit of LongMemEval found as of 2026-10-13. Checked: all 56 items on the LongMemEval tracker (titles; the 16 data-error items read in full), and the titles of the 40 newest arXiv papers mentioning LongMemEval (2026-08-29 to 2026-10-09), with five abstracts read. Not checked: OpenReview, Semantic Scholar citation lists, Hacker News, Reddit, vendor blogs since the 2026-10-13 research notes.

**V2:** LongMemEval-V2 (arXiv 2605.12493, repository created 2026-05-11) is a different benchmark: 451 new questions over web-agent trajectories. It does not reuse the 500 conversational questions, so it does not correct or replace this answer key.

**Cautions recorded at the gate**
- The owner replied to data-error reports up to 2025-12-22 and to none of the 2026 reports. The original repository was last pushed 2026-05-11; V2 was last pushed 2026-08-09. A maintainer response is possible, not expected.
- Three reported errors the owner agreed to fix (370a8ff4, dd2973ad, 51a45a95) are still present per the open issues; 370a8ff4 has been reported four times.
- Publicly reported so far: 13 distinct question IDs (one withdrawn by its reporter), one structural report on the S file, and an 8-row dossier in arXiv 2609.38021 whose question IDs are not yet extracted. See `prior_reports.csv`.
- The closest prior work, arXiv 2609.38021, is by the author of a memory product and states that no third-party adjudicator checked its dossier.
- The existing LoCoMo audit (dial481/locomo-audit) names its auditor as an LLM "with human review". An audit here that is read by a human first is a difference worth stating, and it means any model pass must be labelled as a model pass.

**Decision:** gate passed. Proceed to preregistration.

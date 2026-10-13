# longmemeval-key-audit

A preregistered audit of the LongMemEval answer key: for each of the 500 questions, does the benchmark's own evidence support the gold answer and the evidence labels?

**Status (2026-10-13):** protocol frozen, annotation not started. There are no findings yet.

## What is here

| File | What it is |
|---|---|
| `PLAN.md` | The preregistration, frozen at tag `prereg-v1` before any sampled gold answer was read |
| `GATE.md` | The prior-work check run before starting, and what it did not cover |
| `prior_reports.csv` | Every publicly reported error found so far, with its source. These are other people's reports, verified separately and never counted as findings of this audit |
| `counts.json` | Structural counts of the audited file, with its revision hash and SHA-256 |
| `sample_v01.json` | The seeded 120-question sample for the first release |
| `scripts/` | `load_counts.py` and `sample.py`, which produce the two files above |

## Data

`longmemeval_oracle.json` from [xiaowu0162/longmemeval-cleaned](https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned), revision `98d7416c24c778c2fee6e6f3006e7a073259d48f`. The data is not redistributed here. Download it into `data/`.

## Reproduce

```
python -I scripts/load_counts.py data/longmemeval_oracle.json counts.json 98d7416c24c778c2fee6e6f3006e7a073259d48f
python -I scripts/sample.py data/longmemeval_oracle.json prior_reports.csv sample_v01.json
```

Both commands rewrite the committed file with identical content.

## Interest

The auditor has no commercial memory product. He builds research memory systems and has a paper under review that reports a LoCoMo retrieval result.

## Licence

MIT. LongMemEval is by Wu et al. (ICLR 2025) and is MIT licensed.

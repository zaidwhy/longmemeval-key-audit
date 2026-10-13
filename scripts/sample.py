"""Draw the seeded, stratified first-release sample. Reads question IDs and types only, never answers.

Usage: python -I scripts/sample.py data/longmemeval_oracle.json prior_reports.csv sample_v01.json
"""
import csv
import json
import random
import sys

SEED = 20261013
SAMPLE_SIZE = 120


def main(data_path, prior_path, out_path):
    data = json.load(open(data_path, encoding="utf-8"))
    known = {q["question_id"] for q in data}

    with open(prior_path, encoding="utf-8", newline="") as f:
        prior = sorted({row["question_id"] for row in csv.DictReader(f)} & known)

    # Strata: abstention questions form their own stratum; the rest are grouped by question_type.
    strata = {}
    for q in data:
        if q["question_id"] in prior:
            continue
        key = "abstention" if q["question_id"].endswith("_abs") else q["question_type"]
        strata.setdefault(key, []).append(q["question_id"])

    pool = sum(len(ids) for ids in strata.values())
    rng = random.Random(SEED)
    sample = {}
    # Largest-remainder allocation so the stratum sizes sum to SAMPLE_SIZE exactly.
    exact = {k: SAMPLE_SIZE * len(v) / pool for k, v in strata.items()}
    alloc = {k: int(x) for k, x in exact.items()}
    for k in sorted(exact, key=lambda k: (-(exact[k] - alloc[k]), k))[: SAMPLE_SIZE - sum(alloc.values())]:
        alloc[k] += 1
    for k in sorted(strata):
        sample[k] = sorted(rng.sample(sorted(strata[k]), alloc[k]))

    out = {
        "seed": SEED,
        "sample_size": SAMPLE_SIZE,
        "pool_excluding_prior_reported": pool,
        "prior_reported_stratum": prior,
        "stratum_pool_sizes": {k: len(v) for k, v in sorted(strata.items())},
        "stratum_sample_sizes": {k: len(v) for k, v in sample.items()},
        "sample": sample,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
        f.write("\n")
    print(json.dumps({k: out[k] for k in out if k != "sample"}, indent=2))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])

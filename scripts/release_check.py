"""Check the definite-tier rules of PLAN.md amendment A1 before a release. Prints counts and question IDs only.

Usage: python -I scripts/release_check.py annotations/first.jsonl

Exit status 1 if any definite call lacks a verbatim quote or a confirming label from a later calendar day.
"""
import json
import sys
from collections import Counter


def read_events(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def check(events):
    locks, labels = {}, {}
    for e in events:
        if e.get("event") == "lock":
            locks.setdefault(e["question_id"], e)
        elif e.get("event") == "label":
            labels.setdefault(e["question_id"], []).append(e)

    codes, tiers = Counter(), Counter()
    no_quote, no_second_look = [], []
    for qid, history in sorted(labels.items()):
        latest = history[-1]
        codes[latest["code"]] += 1
        if latest["code"] == "OK":
            continue
        tiers[latest["tier"]] += 1
        if latest["tier"] != "definite":
            continue
        if not locks[qid].get("quote", "").strip():
            no_quote.append(qid)
        # Confirmed means: the latest label is definite and an earlier label exists from an earlier UTC day.
        first_day = history[0]["timestamp"][:10]
        if latest["timestamp"][:10] <= first_day:
            no_second_look.append(qid)

    return {
        "locked": len(locks),
        "labelled": len(labels),
        "by_code": dict(sorted(codes.items())),
        "non_ok_by_tier": dict(sorted(tiers.items())),
        "definite_without_quote": no_quote,
        "definite_without_later_day_confirmation": no_second_look,
    }


def main(path):
    result = check(read_events(path))
    print(json.dumps(result, indent=2))
    failed = result["definite_without_quote"] or result["definite_without_later_day_confirmation"]
    print("RELEASE CHECK: " + ("FAIL" if failed else "PASS"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))

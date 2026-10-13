"""Print structural counts for longmemeval_oracle.json without displaying any gold answer.

Usage: python -I scripts/load_counts.py data/longmemeval_oracle.json counts.json <hf_revision>
"""
import hashlib
import json
import sys
from collections import Counter


def main(path, out_path, revision):
    raw = open(path, "rb").read()
    data = json.loads(raw.decode("utf-8"))

    types = Counter(q["question_type"] for q in data)
    abstention = [q["question_id"] for q in data if q["question_id"].endswith("_abs")]
    non_string = Counter(type(q["answer"]).__name__ for q in data if not isinstance(q["answer"], str))

    evidence_turns = []
    no_evidence_turn = []
    for q in data:
        n = sum(1 for session in q["haystack_sessions"] for turn in session if turn.get("has_answer"))
        evidence_turns.append(n)
        if n == 0:
            no_evidence_turn.append(q["question_id"])

    ids = [q["question_id"] for q in data]
    counts = {
        "file": path.replace("\\", "/").split("/")[-1],
        "hf_dataset": "xiaowu0162/longmemeval-cleaned",
        "hf_revision": revision,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "questions": len(data),
        "unique_question_ids": len(set(ids)),
        "fields": sorted(data[0].keys()),
        "per_question_type": dict(sorted(types.items())),
        "abstention_ids": len(abstention),
        "non_string_answers_by_type": dict(non_string),
        "answer_sessions_per_question": dict(sorted(Counter(len(q["answer_session_ids"]) for q in data).items())),
        "evidence_turns_per_question": dict(sorted(Counter(evidence_turns).items())),
        "questions_with_no_evidence_turn": len(no_evidence_turn),
        "abstention_among_no_evidence_turn": sum(1 for i in no_evidence_turn if i.endswith("_abs")),
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(counts, f, indent=2)
        f.write("\n")
    print(json.dumps(counts, indent=2))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])

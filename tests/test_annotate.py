"""Tests for tools/annotate.py on a small synthetic dataset. Run: python -m unittest discover -s tests"""
import contextlib
import csv
import hashlib
import http.client
import io
import json
import os
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import annotate  # noqa: E402

IDS = ["q_a", "q_b", "q_c", "q_d_abs", "q_e"]


def make_item(qid, n):
    sessions = [[{"role": "user", "content": f"user text {qid} s{s}"},
                 {"role": "assistant", "content": f"assistant text {qid} s{s}", **({"has_answer": True} if s == 0 else {})}]
                for s in range(2)]
    return {"question_id": qid, "question_type": "multi-session" if n % 2 else "temporal-reasoning",
            "question": f"What about {qid}?", "question_date": "2023/05/30 (Tue) 10:00",
            "answer": f"GOLD-SECRET-{n}" if n != 3 else 33, "answer_session_ids": [f"{qid}_s0"],
            "haystack_session_ids": [f"{qid}_s0", f"{qid}_s1"],
            "haystack_dates": ["2023/05/01 (Mon) 09:00", "2023/05/02 (Tue) 09:00"], "haystack_sessions": sessions}


class Fixture:
    def __init__(self, sha=None):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.data = os.path.join(d, "data.json")
        with open(self.data, "w", encoding="utf-8") as f:
            json.dump([make_item(q, n) for n, q in enumerate(IDS)], f)
        with open(self.data, "rb") as f:
            real = hashlib.sha256(f.read()).hexdigest()
        self.counts = os.path.join(d, "counts.json")
        with open(self.counts, "w") as f:
            json.dump({"sha256": sha or real}, f)
        self.prior = os.path.join(d, "prior.csv")
        with open(self.prior, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["question_id", "source_url", "reported", "reporter", "claim", "owner_response", "read_on"])
            w.writerow(["q_e", "http://x/1", "2025", "rep1", "PRIOR-CLAIM-SECRET", "no reply", "2026"])
            w.writerow(["q_a", "http://x/2", "2025", "rep2", "PRIOR-CLAIM-SECRET-2", "none", "2026"])
            w.writerow(["not_in_data", "http://x/3", "2025", "rep3", "ghost", "none", "2026"])
        self.sample = os.path.join(d, "sample.json")
        with open(self.sample, "w") as f:
            json.dump({"prior_reported_stratum": ["q_a", "q_e"],
                       "sample": {"temporal-reasoning": ["q_c", "q_b"], "abstention": ["q_d_abs"]}}, f)
        self.ann = os.path.join(d, "annotations")

    def store(self, pass_name="t", ids_file=None, log_session=True):
        return annotate.Store(self.data, self.counts, self.prior, self.sample, self.ann, pass_name, ids_file, log_session)

    def jsonl(self, pass_name="t"):
        p = os.path.join(self.ann, pass_name + ".jsonl")
        with open(p, encoding="utf-8") as f:
            return [json.loads(x) for x in f if x.strip()]


class Live:
    """A real server on an ephemeral port in a thread; shut down cleanly on exit."""

    def __init__(self, store):
        self.server = annotate.make_server(store, 0)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *a):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)

    def req(self, method, path, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request(method, path, json.dumps(body) if body is not None else None, {"Content-Type": "application/json"})
        r = c.getresponse()
        raw = r.read()
        c.close()
        return r.status, raw


def J(raw):
    return json.loads(raw)


class AnnotateTests(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()
        self.addCleanup(self.fx.tmp.cleanup)

    def test_queue_order(self):
        # prior-reported first (sorted; ids missing from the data dropped), then sample strata in sorted key
        # order ("abstention" before "temporal-reasoning"), ids in the listed order within a stratum
        s = self.fx.store()
        self.assertEqual(s.queue, [("q_a", "prior-reported"), ("q_e", "prior-reported"), ("q_d_abs", "abstention"),
                                   ("q_c", "temporal-reasoning"), ("q_b", "temporal-reasoning")])

    def test_ids_file_overrides_queue(self):
        p = os.path.join(self.fx.tmp.name, "ids.json")
        with open(p, "w") as f:
            json.dump(["q_c", "q_a"], f)
        self.assertEqual([q for q, _ in self.fx.store("blind", p).queue], ["q_c", "q_a"])

    def test_prelock_has_no_gold(self):
        with Live(self.fx.store()) as srv:
            for qid in IDS:
                status, raw = srv.req("GET", f"/api/item/{qid}")
                self.assertEqual(status, 200)
                for bad in (b"GOLD-SECRET", b"has_answer", b"answer_session_ids", b"PRIOR-CLAIM", b"rep1"):
                    self.assertNotIn(bad, raw)
                self.assertEqual(sorted(J(raw)), ["question", "question_date", "question_id", "question_type",
                                                  "sessions", "status"])
            status, raw = srv.req("GET", "/api/state")
            self.assertEqual(status, 200)
            self.assertIn(b"q_e", raw)
            self.assertNotIn(b"GOLD-SECRET", raw)
            self.assertNotIn(b"PRIOR-CLAIM", raw)

    def test_reveal_refused_before_lock(self):
        with Live(self.fx.store()) as srv:
            status, raw = srv.req("GET", "/api/reveal/q_a")
            self.assertEqual(status, 403)
            self.assertNotIn(b"GOLD-SECRET", raw)

    def test_reveal_after_lock(self):
        with Live(self.fx.store()) as srv:
            status, raw = srv.req("POST", "/api/lock", {"question_id": "q_a", "answer": "mine", "quote": "q"})
            self.assertEqual(status, 200)
            self.assertNotIn(b"GOLD-SECRET", raw)
            status, raw = srv.req("GET", "/api/reveal/q_a")
            r = J(raw)
            self.assertEqual(status, 200)
            self.assertEqual(r["gold"], "GOLD-SECRET-0")
            self.assertEqual(r["answer_session_ids"], ["q_a_s0"])
            self.assertEqual(r["evidence_turns"], [{"session_id": "q_a_s0", "turn": 1}])
            self.assertEqual(r["prior_reports"][0]["claim"], "PRIOR-CLAIM-SECRET-2")
            self.assertEqual(J(srv.req("GET", "/api/item/q_a")[1])["lock"]["answer"], "mine")

    def test_int_gold_is_string(self):
        s = self.fx.store()
        s.lock("q_d_abs", "x", "", False)
        self.assertEqual(s.reveal("q_d_abs")["gold"], "33")

    def test_second_lock_rejected(self):
        with Live(self.fx.store()) as srv:
            self.assertEqual(srv.req("POST", "/api/lock", {"question_id": "q_a", "answer": "first"})[0], 200)
            self.assertEqual(srv.req("POST", "/api/lock", {"question_id": "q_a", "answer": "second"})[0], 409)
            self.assertEqual(J(srv.req("GET", "/api/item/q_a")[1])["lock"]["answer"], "first")
        locks = [e for e in self.fx.jsonl() if e["event"] == "lock"]
        self.assertEqual([e["answer"] for e in locks], ["first"])

    def test_empty_answer_rejected_and_not_answerable_fills(self):
        s = self.fx.store()
        with self.assertRaises(annotate.ToolError):
            s.lock("q_a", "   ", "", False)
        s.lock("q_a", "", "", True)
        self.assertEqual(s.locks["q_a"]["answer"], annotate.NOT_ANSWERABLE_TEXT)
        self.assertTrue(s.locks["q_a"]["not_answerable"])

    def test_label_requires_lock(self):
        with Live(self.fx.store()) as srv:
            status, _ = srv.req("POST", "/api/label", {"question_id": "q_a", "code": "OK", "justification": "j"})
            self.assertEqual(status, 403)
        self.assertEqual([e["event"] for e in self.fx.jsonl()], ["session"])

    def test_tier_required_for_non_ok(self):
        s = self.fx.store()
        s.lock("q_a", "mine", "", False)
        with self.assertRaises(annotate.ToolError):
            s.label("q_a", {"code": "WRONG_GOLD", "justification": "j"})
        with self.assertRaises(annotate.ToolError):
            s.label("q_a", {"code": "NOPE", "justification": "j"})
        with self.assertRaises(annotate.ToolError):
            s.label("q_a", {"code": "OK", "justification": " "})
        self.assertNotIn("q_a", s.labels)
        s.label("q_a", {"code": "OK", "tier": "definite", "justification": "matches"})
        self.assertIsNone(s.labels["q_a"][-1]["tier"])
        s.label("q_a", {"code": "WRONG_GOLD", "tier": "definite", "evidence_label": True, "justification": "j"})
        self.assertTrue(s.labels["q_a"][-1]["evidence_label"])

    def test_label_revision_appends_latest_wins(self):
        s = self.fx.store()
        s.lock("q_a", "mine", "", False)
        s.label("q_a", {"code": "OK", "justification": "first"})
        r = s.label("q_a", {"code": "MULTIPLE", "tier": "ambiguous", "justification": "second"})
        self.assertEqual(r["label"]["code"], "MULTIPLE")
        self.assertEqual(r["label_revisions"], 1)
        self.assertEqual([e["event"] for e in self.fx.jsonl()], ["session", "lock", "label", "label"])
        self.assertEqual(self.fx.store().labels["q_a"][-1]["justification"], "second")

    def test_event_fields(self):
        s = self.fx.store()
        s.lock("q_a", "mine", "quote", False)
        s.label("q_a", {"code": "OK", "justification": "j", "note": "n"})
        sess, lock, label = self.fx.jsonl()
        for e in (sess, lock, label):
            self.assertEqual(e["pass"], "t")
            self.assertEqual(e["schema"], annotate.SCHEMA)
            self.assertTrue(e["timestamp"].endswith("Z"))
        self.assertEqual(sess["data_sha256"], s.sha)
        self.assertEqual((lock["answer"], lock["quote"], lock["not_answerable"]), ("mine", "quote", False))
        self.assertEqual((label["code"], label["evidence_label"], label["tier"], label["justification"], label["note"]),
                         ("OK", False, None, "j", "n"))

    def test_resume_picks_next_item(self):
        s = self.fx.store()
        s.lock("q_a", "m", "", False)
        s.label("q_a", {"code": "OK", "justification": "j"})
        s.lock("q_e", "m", "", False)  # locked, not labelled
        s2 = self.fx.store()
        st = s2.state()
        self.assertEqual(st["first_open"], 1)
        self.assertEqual(st["queue"][1]["status"], "locked")
        self.assertEqual(st["labelled"], 1)
        s2.label("q_e", {"code": "OK", "justification": "j"})
        self.assertEqual(self.fx.store().state()["first_open"], 2)

    def test_passes_are_isolated(self):
        s = self.fx.store("first")
        s.lock("q_a", "m", "", False)
        self.assertEqual(self.fx.store("second").status("q_a"), "new")

    def test_sha_mismatch_refuses_to_start(self):
        fx = Fixture(sha="0" * 64)
        self.addCleanup(fx.tmp.cleanup)
        with self.assertRaises(SystemExit):
            fx.store()
        self.assertFalse(os.path.exists(fx.ann))

    def test_summary_has_counts_only(self):
        s = self.fx.store()
        s.lock("q_a", "MY-ANSWER-TEXT", "MY-QUOTE-TEXT", False)
        s.label("q_a", {"code": "WRONG_GOLD", "tier": "definite", "justification": "JUST-TEXT", "note": "NOTE-TEXT"})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            annotate.main(["--pass", "t", "--summary", "--data", self.fx.data, "--counts", self.fx.counts,
                           "--prior", self.fx.prior, "--sample", self.fx.sample, "--annotations", self.fx.ann])
        text = out.getvalue()
        for bad in ("GOLD-SECRET", "MY-ANSWER", "MY-QUOTE", "JUST-TEXT", "NOTE-TEXT", "PRIOR-CLAIM"):
            self.assertNotIn(bad, text)
        summ = json.loads(text)
        self.assertEqual((summ["locked"], summ["labelled"], summ["per_code"], summ["per_tier"]),
                         (1, 1, {"WRONG_GOLD": 1}, {"definite": 1}))
        self.assertEqual(summ["per_stratum"]["prior-reported"]["labelled"], 1)
        self.assertEqual(sum(e["event"] == "session" for e in self.fx.jsonl()), 1)  # --summary logs no session

    def test_bad_host_rejected(self):
        with Live(self.fx.store()) as srv:
            c = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=5)
            c.request("GET", "/api/state", headers={"Host": "evil.example:80"})
            self.assertEqual(c.getresponse().status, 403)
            c.close()

    def test_unknown_id_404(self):
        with Live(self.fx.store()) as srv:
            self.assertEqual(srv.req("GET", "/api/item/nope")[0], 404)


if __name__ == "__main__":
    unittest.main()

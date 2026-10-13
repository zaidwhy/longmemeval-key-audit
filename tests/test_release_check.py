"""Tests for scripts/release_check.py. Run: python -m unittest discover -s tests"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import release_check  # noqa: E402


def lock(qid, quote="a verbatim quote"):
    return {"event": "lock", "question_id": qid, "answer": "x", "quote": quote, "timestamp": "2026-10-14T10:00:00Z"}


def label(qid, code, tier, day):
    return {"event": "label", "question_id": qid, "code": code, "tier": tier, "timestamp": f"2026-10-{day}T10:00:00Z"}


class ReleaseCheckTest(unittest.TestCase):
    def test_ok_and_ambiguous_need_no_confirmation(self):
        r = release_check.check([lock("a"), label("a", "OK", None, 14), lock("b"), label("b", "WRONG_GOLD", "ambiguous", 14)])
        self.assertEqual(r["definite_without_later_day_confirmation"], [])
        self.assertEqual(r["by_code"], {"OK": 1, "WRONG_GOLD": 1})

    def test_definite_same_day_fails(self):
        r = release_check.check([lock("a"), label("a", "WRONG_GOLD", "definite", 14), label("a", "WRONG_GOLD", "definite", 14)])
        self.assertEqual(r["definite_without_later_day_confirmation"], ["a"])

    def test_definite_confirmed_on_later_day_passes(self):
        r = release_check.check([lock("a"), label("a", "WRONG_GOLD", "definite", 14), label("a", "WRONG_GOLD", "definite", 15)])
        self.assertEqual(r["definite_without_later_day_confirmation"], [])
        self.assertEqual(r["definite_without_quote"], [])

    def test_downgrade_on_second_look_is_not_definite(self):
        r = release_check.check([lock("a"), label("a", "WRONG_GOLD", "definite", 14), label("a", "WRONG_GOLD", "ambiguous", 15)])
        self.assertEqual(r["non_ok_by_tier"], {"ambiguous": 1})
        self.assertEqual(r["definite_without_later_day_confirmation"], [])

    def test_definite_without_quote_fails(self):
        r = release_check.check([lock("a", quote=" "), label("a", "WRONG_GOLD", "definite", 14), label("a", "WRONG_GOLD", "definite", 15)])
        self.assertEqual(r["definite_without_quote"], ["a"])


if __name__ == "__main__":
    unittest.main()

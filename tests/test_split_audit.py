"""Synthetic invariants for the independent split audit; never real catalogue text."""
import itertools
import json
from pathlib import Path
import random
import tempfile
import unittest

from scripts.research import audit_splits as audit


def rows(path, records):
    audit.write_rows(path, records)
    return path


def fixture(root, products=None):
    products = products or [
        {"sku_id": "a", "category_id": "761", "title": "AlphaX-720", "description": None},
        {"sku_id": "b", "category_id": "761", "title": "<b>ALPHAX 720</b>", "description": ""},
        {"sku_id": "c", "category_id": "482", "title": "Unique kettle KE899", "description": None},
        {"sku_id": "d", "category_id": "761", "title": "Isolated Nebula phone Q99", "description": None},
        {"sku_id": "e", "category_id": "482", "title": "Remote Orion vessel K33", "description": None},
    ]
    source = rows(root / "input.jsonl", products)
    splits = rows(root / "split.jsonl", [
        {"sku_id": p["sku_id"], "category_id": p["category_id"], "group_id": "g:" + p["sku_id"],
         "split": "development" if p["sku_id"] == "a" else "validation" if p["sku_id"] == "c" else "test_reserved"}
        for p in products])
    metadata = list(audit.read_jsonl(splits))
    families = rows(root / "family.jsonl", [m | {"family_id": "f:" + m["sku_id"], "known_exposure": False,
                    "family_exposed": False, "mixed_split_family": False} for m in metadata])
    reserve = rows(root / "reserve.jsonl", [m | {"family_id": "f:" + m["sku_id"],
        "text_materialized": False, "attributes": [{"status": "unreviewed", "value": None, "evidence": None}]}
        for m in metadata if m["sku_id"] == "d"])
    summary = root / "summary.json"
    audit.dump(summary, {"artifacts": {p.name: audit.digest(p) for p in [families, reserve]},
        "protected_sources": {str(p): audit.digest(p) for p in [source, splits]}, "known_exposure_rows": 0})
    exposure = rows(root / "seen.jsonl", [{"sku_id": "e", "attributes": [{"value": "MUST_NOT_BE_READ"}]}])
    return source, splits, families, summary, reserve, [exposure]


class SplitAuditTests(unittest.TestCase):
    def test_near_join_matches_bruteforce_pairs_not_only_components(self):
        rng = random.Random(7)
        docs = {str(i): set(rng.sample(range(25), rng.randint(1, 20))) for i in range(70)}
        docs.update(copy=docs["1"].copy(), empty=set())
        for threshold in [.5, .9, 1.0]:
            stats = {}
            actual = {frozenset([a, b]) for a, b, _ in audit.near_pairs(docs, threshold, stats, 10000)}
            expected = {frozenset([a, b]) for a, b in itertools.combinations(docs, 2)
                        if docs[a] | docs[b] and len(docs[a] & docs[b]) / len(docs[a] | docs[b]) >= threshold}
            self.assertEqual(actual, expected)
            self.assertEqual(stats["matches"], len(expected))

    def test_budget_aborts_instead_of_returning_partial_pass(self):
        with self.assertRaisesRegex(ValueError, "budget_exceeded"):
            list(audit.near_pairs({str(i): {1, 2} for i in range(5)}, .9, {}, 1))

    def test_nfkc_html_case_and_yo_normalization(self):
        self.assertEqual(audit.norm("<b>ЁЖ Ｘ</b>&nbsp;A-1"), audit.norm("еж x a 1"))
        self.assertEqual(audit.norm("<script>secret</script>"), "")

    def test_full_audit_quarantines_whole_components_and_keeps_reserve_blind(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            args = fixture(root)
            before = {str(p): audit.digest(p) for p in [*args[:5], *args[5]]}
            report = audit.audit(*args, root / "out")
            self.assertEqual(report["detectors"]["normalized_title"]["cross_split_groups"], 1)
            self.assertEqual(report["mixed_split_components"], 1)
            self.assertEqual(report["known_exposure_rows"], 1)
            self.assertEqual(report["corrected"]["quarantined_rows"], 3)
            self.assertEqual(report["corrected"]["detected_cross_split_components"], 0)
            self.assertEqual(report["reserve"]["status"], "metadata_checks_passed")
            eligible = list(audit.read_jsonl(root / "out/eligible.split_manifest.jsonl"))
            self.assertEqual({r["sku_id"] for r in eligible}, {"c", "d"})
            self.assertEqual(next(r["evaluation_role"] for r in eligible if r["sku_id"] == "c"), "development_feedback")
            self.assertEqual(before, {p: audit.digest(Path(p)) for p in before})
            self.assertEqual(audit.verify(root / "out")["status"], "verified")
            for path in (root / "out").iterdir():
                text = path.read_text(encoding="utf-8")
                for sentinel in ["AlphaX-720", "<b>ALPHAX", "Unique kettle", "MUST_NOT_BE_READ"]:
                    self.assertNotIn(sentinel, text)

    def test_repeated_run_preserves_identical_membership_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            args = fixture(root)
            audit.audit(*args, root / "one")
            audit.audit(*args, root / "two")
            for path in (root / "one").iterdir():
                self.assertEqual(path.read_bytes(), (root / "two" / path.name).read_bytes())
            with self.assertRaisesRegex(ValueError, "new_output"):
                audit.audit(*args, root / "one")

    def test_duplicate_or_missing_sku_and_frozen_mutation_fail_closed(self):
        for change in ["duplicate", "missing", "mutation", "category"]:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                args = fixture(root)
                if change in {"duplicate", "missing", "category"}:
                    p = args[0] if change == "category" else args[1]
                    records = list(audit.read_jsonl(p))
                    if change == "duplicate":
                        records.append(records[0])
                    elif change == "missing":
                        records.pop()
                    else:
                        records[0]["category_id"] = "bad"
                    p.unlink()  # Synthetic fixture only.
                    rows(p, records)
                else:
                    with args[2].open("a", encoding="utf-8") as stream:
                        stream.write("\n")
                with self.assertRaises(ValueError):
                    audit.audit(*args, root / "out")
                self.assertFalse((root / "out/audit.summary.json").exists())

    def test_transitive_links_and_identical_empty_descriptions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            args = fixture(root)
            families = list(audit.read_jsonl(args[2]))
            for r in families:
                if r["sku_id"] in {"a", "c"}:
                    r["family_id"] = "linked"
            args[2].unlink()
            rows(args[2], families)
            summary = json.loads(args[3].read_text())
            summary["artifacts"][args[2].name] = audit.digest(args[2])
            args[3].unlink()
            audit.dump(args[3], summary)
            report = audit.audit(*args, root / "out")
            self.assertEqual(report["corrected"]["quarantined_rows"], 4)
            self.assertNotIn("raw_description", report["detectors"])
            members = list(audit.read_jsonl(root / "out/membership.jsonl"))
            self.assertEqual(len({r["family_id"] for r in members if r["sku_id"] in {"a", "b", "c"}}), 1)

    def test_exposed_or_nonblank_reserve_is_never_reported_safe(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            args = fixture(root)
            new_exposure = rows(root / "new-seen.jsonl", [{"sku_id": "d"}])
            report = audit.audit(*args[:5], args[5] + [new_exposure], root / "out")
            self.assertEqual(report["reserve"]["status"], "quarantine_required")
            self.assertEqual(report["reserve"]["invalid_rows"], 1)

    def test_checksum_verifier_rejects_changed_sources_outputs_and_extra_files(self):
        for change in ["source", "output", "extra"]:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                args = fixture(root)
                audit.audit(*args, root / "out")
                if change == "extra":
                    (root / "out/extra").write_text("unexpected")
                else:
                    path = args[0] if change == "source" else root / "out/membership.jsonl"
                    with path.open("a", encoding="utf-8") as stream:
                        stream.write("\n")
                with self.assertRaises(ValueError):
                    audit.verify(root / "out")

    def test_reserve_with_text_or_populated_label_fails_before_success(self):
        for change in ["text", "label"]:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                args = fixture(root)
                records = list(audit.read_jsonl(args[4]))
                if change == "text":
                    records[0]["title"] = "DO_NOT_EXPORT"
                else:
                    records[0]["attributes"][0]["value"] = "fabricated"
                args[4].unlink()
                rows(args[4], records)
                summary = json.loads(args[3].read_text())
                summary["artifacts"][args[4].name] = audit.digest(args[4])
                args[3].unlink()
                audit.dump(args[3], summary)
                with self.assertRaisesRegex(ValueError, "reserve_"):
                    audit.audit(*args, root / "out")
                self.assertFalse((root / "out/audit.summary.json").exists())

    def test_entirely_quarantined_partition_is_valid_but_reserve_is_flagged(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            args = fixture(root)
            records = list(audit.read_jsonl(args[1]))
            for r in records:
                r["group_id"] = "one-crossing-group"
            args[1].unlink()
            rows(args[1], records)
            families = list(audit.read_jsonl(args[2]))
            for r in families:
                r["group_id"] = "one-crossing-group"
            args[2].unlink()
            rows(args[2], families)
            reserve = list(audit.read_jsonl(args[4]))
            reserve[0]["group_id"] = "one-crossing-group"
            args[4].unlink()
            rows(args[4], reserve)
            summary = json.loads(args[3].read_text())
            summary["artifacts"] = {p.name: audit.digest(p) for p in [args[2], args[4]]}
            summary["protected_sources"][str(args[1])] = audit.digest(args[1])
            args[3].unlink()
            audit.dump(args[3], summary)
            report = audit.audit(*args, root / "out")
            self.assertEqual(report["corrected"]["eligible_rows"], 0)
            self.assertEqual(report["reserve"]["invalid_rows"], 1)
            self.assertEqual(audit.verify(root / "out")["status"], "verified")


if __name__ == "__main__":
    unittest.main()

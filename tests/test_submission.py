"""Submission boundary and history checks using disposable local Git repos."""
from contextlib import redirect_stdout
import hashlib
import io
import json
import posixpath
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import unquote, urlsplit

from scripts.release import publish_gitea as publication

PROJECT = Path(__file__).resolve().parents[1]


class SubmissionTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.root = self.folder / "source"
        self.root.mkdir()
        self.git("init", "-b", "main", "--quiet")
        self.git("config", "user.name", "Synthetic QA")
        self.git("config", "user.email", "qa@example.invalid")
        self.git("config", "core.autocrlf", "false")
        self.source = self.commit({
            "README.md": "# Development\n[Thoughts](RESEARCH.md)\n",
            publication.README_SOURCE: (PROJECT / publication.README_SOURCE).read_text(encoding="utf-8"),
            "pyproject.toml": "[project]\nname='synthetic'\nversion='0.0.0'\n",
            "src/goodsai/cli.py": "# executable code\n",
            "src/goodsai/baseline.json": "{}\n",
            "docs/QUICKSTART.md": "# Quickstart\n[Evidence](research/results.md#limits)\n[API](RESPONSES.md)\n",
            "docs/RESPONSES.md": "# API\n",
            "scripts/research/tool.py": "# executable evaluation tool\n",
            "scripts/research/human_gold_form.html": "<html></html>\n",
            "tests/fixtures/test/products.jsonl": "{}\n",
            "AGENTS.md": "private instructions\n",
            "TASKS.md": "private task board\n",
            "RESEARCH.md": "private thoughts\n",
            "docs/PROJECT_STATUS.md": "private chronology\n",
            "docs/research/results.md": "private research\n",
            "docs/reviews/next.md": "private review\n",
            "docs/unknown-new-document.md": "new prose must stay private\n",
            "scripts/research/notes.md": "private tool notes\n",
            "src/goodsai/notes.md": "private runtime notes\n",
            "outputs/tracked-secret.json": "must never be published\n",
            "data/accidentally-tracked.json": "must never be published\n",
            ".env": "must never be published\n",
        })

    def git(self, *args, data=None):
        return publication.git(self.root, *args, data=data).decode().strip()

    def commit(self, files):
        for name, content in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
        self.git("add", ".")
        self.git("commit", "--quiet", "-m", "Synthetic source")
        return self.git("rev-parse", "HEAD")

    def prepare(self, source=None, parent=None):
        return publication.prepare(self.root, source or self.source, parent or self.source)

    def test_allowlist_and_submission_readme_keep_internal_prose_out(self):
        files = publication.submission_files(self.root, self.source)
        self.assertIn("src/goodsai/cli.py", files)
        self.assertIn("scripts/research/tool.py", files)
        self.assertIn("scripts/research/human_gold_form.html", files)
        self.assertIn("tests/fixtures/test/products.jsonl", files)
        for name in publication.entries(self.root, self.source):
            if name not in files and name != "README.md":
                self.assertFalse(publication.allowed(name), name)
        self.assertNotIn(b"Thoughts", files["README.md"][1])
        self.assertNotIn(b"private", files["README.md"][1])
        quickstart = files["docs/QUICKSTART.md"][1].decode()
        self.assertIn(f"{publication.SOURCE_REPOSITORY}/blob/{self.source}/docs/research/results.md#limits", quickstart)
        self.assertIn("[API](RESPONSES.md)", quickstart)

    def test_current_repository_export_has_working_links_and_unchanged_runtime(self):
        source = publication.resolve(PROJECT, "HEAD")
        files = publication.submission_files(PROJECT, source)
        for name in ("AGENTS.md", "CONTRIBUTING.md", "TASKS.md", "RESEARCH.md", "docs/PROJECT_STATUS.md"):
            self.assertNotIn(name, files)
        self.assertFalse(any(name.startswith(("docs/research/", "docs/reviews/", ".github/")) for name in files))
        for name, (_, data) in files.items():
            if name.endswith(".py"):
                self.assertEqual(data, publication.git(PROJECT, "show", f"{source}:{name}"), name)
            if not name.endswith(".md"):
                continue
            for match in publication.LINK.finditer(data.decode("utf-8")):
                url = urlsplit(match[2])
                if url.scheme or url.netloc or not url.path or url.path.startswith("/"):
                    continue
                target = posixpath.normpath(posixpath.join(posixpath.dirname(name), unquote(url.path)))
                present = target in files or any(path.startswith(target.rstrip("/") + "/") for path in files)
                self.assertTrue(present, f"Broken submission link in {name}: {match[2]}")
        self.assertIn(b"](docs/QUICKSTART.md)", files["README.md"][1])
        self.assertIn(b"](../../docs/QUICKSTART.md)", files[publication.README_SOURCE][1])
        quality = files["reports/quality_20261021.json"][1]
        self.assertNotIn(b"\r", quality)
        self.assertNotIn(b"\r", files["reports/quality_20261021.md"][1])
        self.assertIn(hashlib.sha256(quality).hexdigest().encode(), files["docs/RESULTS.md"][1])
        self.assertEqual(json.loads(quality)["provenance"]["exporter_sha256"],
                         hashlib.sha256(files["scripts/research/export_quality_report.py"][1]).hexdigest())

    def test_migration_is_fast_forward_and_manifest_matches_every_file(self):
        before = self.git("status", "--porcelain")
        result = self.prepare()
        commit = result["gitea_sha"]
        self.assertEqual(self.git("rev-parse", f"{commit}^"), self.source)
        self.assertTrue(publication.ancestor(self.root, self.source, commit))
        self.assertEqual(before, self.git("status", "--porcelain"))
        manifest = json.loads(self.git("show", f"{commit}:{publication.MANIFEST}"))
        self.assertEqual(manifest["source_sha"], self.source)
        tracked = publication.entries(self.root, commit)
        self.assertEqual(set(manifest["files_sha256"]), set(tracked) - {publication.MANIFEST})
        for name, expected in manifest["files_sha256"].items():
            actual = publication.git(self.root, "show", f"{commit}:{name}")
            self.assertEqual(expected, hashlib.sha256(actual).hexdigest())

    def test_uses_committed_objects_even_with_dirty_worktree(self):
        (self.root / "src/goodsai/cli.py").write_text("dirty code\n", encoding="utf-8")
        result = self.prepare()
        self.assertEqual(self.git("show", f"{result['gitea_sha']}:src/goodsai/cli.py"), "# executable code")
        self.assertIn("src/goodsai/cli.py", self.git("status", "--porcelain"))

    def test_future_publication_does_not_push_development_history_and_is_idempotent(self):
        first = self.prepare()["gitea_sha"]
        source = self.commit({"docs/research/new.md": "unique private thought from future\n",
                              "src/goodsai/cli.py": "# next executable version\n"})
        second = self.prepare(source, first)["gitea_sha"]
        self.assertEqual(self.git("rev-parse", f"{second}^"), first)
        self.assertFalse(publication.ancestor(self.root, source, second))
        self.assertNotIn("docs/research/new.md", self.git("rev-list", "--objects", f"{first}..{second}"))
        self.assertEqual(self.git("show", f"{second}:src/goodsai/cli.py"), "# next executable version")
        self.assertEqual(self.prepare(source, second)["gitea_sha"], second)
        self.assertFalse(self.prepare(source, second)["changed"])

    def test_stale_source_is_rejected(self):
        first = self.prepare()["gitea_sha"]
        source = self.commit({"src/goodsai/cli.py": "# next version\n"})
        second = self.prepare(source, first)["gitea_sha"]
        with self.assertRaisesRegex(publication.PublicationError, "newer"):
            self.prepare(self.source, second)

    def test_unknown_history_and_manual_commits_are_rejected(self):
        tree = self.git("rev-parse", f"{self.source}^{{tree}}")
        unknown = self.git("commit-tree", tree, data=b"Unrelated history\n")
        with self.assertRaisesRegex(publication.PublicationError, "Unrecognized"):
            self.prepare(parent=unknown)
        first = self.prepare()["gitea_sha"]
        tree = self.git("rev-parse", f"{first}^{{tree}}")
        manual = self.git("commit-tree", tree, "-p", first, data=b"Manual empty Gitea commit\n")
        with self.assertRaisesRegex(publication.PublicationError, "manual commit"):
            self.prepare(parent=manual)
        # A direct edit retaining the old marker must never be silently overwritten.
        self.git("switch", "--detach", first, "--quiet")
        changed = self.commit({"src/goodsai/cli.py": "# manual Gitea code\n"})
        with self.assertRaisesRegex(publication.PublicationError, "differ"):
            self.prepare(parent=changed)

    def test_selected_symlink_is_rejected(self):
        oid = self.git("hash-object", "-w", "--stdin", data=b"../../.env")
        self.git("update-index", "--add", "--cacheinfo", f"120000,{oid},src/goodsai/link.py")
        tree = self.git("write-tree")
        source = self.git("commit-tree", tree, "-p", self.source, data=b"Synthetic symlink\n")
        with self.assertRaisesRegex(publication.PublicationError, "symlink"):
            self.prepare(source=source)

    def test_main_publishes_to_local_bare_remote_and_verifies_head(self):
        remote = self.folder / "gitea.git"
        subprocess.run(["git", "init", "--bare", "--quiet", str(remote)], check=True)
        self.git("remote", "add", "gitea", str(remote))
        self.git("push", "gitea", f"{self.source}:refs/heads/main")
        report = self.folder / "publication.json"
        args = ["publish_gitea.py", "--source", self.source, "--output", str(report)]
        with patch.object(publication, "ROOT", self.root), patch("sys.argv", args), redirect_stdout(io.StringIO()):
            publication.main()
            first = json.loads(report.read_text(encoding="utf-8"))
            publication.main()
            second = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(first["gitea_sha"], second["gitea_sha"])
        self.assertFalse(second["changed"])
        head = self.git("ls-remote", "gitea", "refs/heads/main").split()[0]
        self.assertEqual(first["gitea_sha"], head)
        self.assertNotIn("TASKS.md", publication.entries(self.root, head))


if __name__ == "__main__":
    unittest.main()

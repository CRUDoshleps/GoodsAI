"""Publish the submission tree, without merging GitHub's development history."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import subprocess
import tempfile
from urllib.parse import quote, unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
SOURCE_REPOSITORY = "https://github.com/CRUDoshleps/GoodsAI"
MANIFEST = "submission-manifest.json"
README_SOURCE = "scripts/release/submission_readme.md"
# New prose is private to development until explicitly approved here. Executable
# tools in scripts/research are retained: tests and evaluation use them.
PUBLIC_FILES = frozenset({
    "docs/ATTRIBUTE_SHADOW.md",
    "docs/STORAGE_PILOT.md",
    "reports/storage_pilot_20261022.json", "reports/storage_pilot_20261022.md",
    "docs/STORAGE_SHADOW.md",
    "reports/storage_shadow_20261022.json", "reports/storage_shadow_20261022.md",
    ".env.example", ".gitattributes", ".gitignore", "pyproject.toml", "TECHNICAL_SPEC.md",
    "configs/production.example.json", "deploy/systemd/goodsai.service", README_SOURCE,
    "requirements/clean-run.in", "requirements/clean-run.lock",
    "scripts/research/human_gold_form.html", "scripts/research/requirements.txt",
    "reports/metrics.md", "reports/run_stats.json",
    "reports/quality_20261021.json", "reports/quality_20261021.md",
    "reports/qa002_20261021.json", "reports/qa002_20261021.md", "docs/QA_ACCEPTANCE.md",
    "docs/DICTIONARY_CONSOLE.md", "docs/REVIEW_PRIORITY.md", "docs/DRIFT.md", "docs/SPAN_SELECTOR.md", "docs/CONTEXT_PLANNER.md", "docs/EXACT_CACHE.md", "docs/ARCHITECTURE.md", "docs/ARTIFACT_BUNDLE.md", "docs/BATTERY_UNITS.md",
    "docs/CATEGORY_REGISTRY.md", "docs/CLEAN_RUN.md", "docs/CONFIGURATION.md",
    "docs/DATASET.md", "docs/EVALUATION.md", "docs/EXPERIMENTAL_GLINER.md",
    "docs/EXTERNAL_ACCEPTANCE.md", "docs/FUZZ_TESTING.md", "docs/HUMAN_GOLD.md",
    "docs/HUMAN_GOLD_GUIDELINES.md", "docs/LLM.md", "docs/QUICKSTART.md",
    "docs/RELATION_VERIFIER.md", "docs/VERIFIER.md", "docs/REQUIREMENTS.md", "docs/RESPONSES.md",
    "docs/RESULTS.md", "docs/RUNBOOK.md", "docs/SILVER_EVALUATION.md", "docs/SCENARIO_MATRIX.md",
    "docs/SPAN_INDEX.md", "docs/SPLIT_AUDIT.md", "docs/examples/release-spec.example.json",
    "docs/delivery/2026-10-19/README.md", "docs/delivery/2026-10-19/bundle.manifest.json",
    "docs/delivery/2026-10-19/checkpoint.json", "docs/delivery/2026-10-19/eda.md",
    "docs/delivery/2026-10-19/metrics.json", "docs/delivery/2026-10-19/pipeline.json",
    "docs/delivery/2026-10-19/technical_slides.md", "docs/delivery/2026-10-19/technical_slides.pdf",
    "docs/product-stage/README.md", "docs/product-stage/SOURCE_MANIFEST.json",
    "docs/product-stage/context/README.md", "docs/product-stage/context/case/attribute-extraction-case.pdf",
    "docs/product-stage/context/case/platform-requirements.md",
    "docs/product-stage/presentation/GoodsAI_Product_Checkpoint_Final.pdf",
    "docs/product-stage/presentation/GoodsAI_Product_Checkpoint_Final.pptx",
})
LINK = re.compile(r"(!?\[[^\]\n]*\]\()([^\s)]+)([^)\n]*\))")
SHA = re.compile(r"[0-9a-f]{40}\Z")


class PublicationError(ValueError):
    pass


def git(root, *args, data=None, env=None):
    return subprocess.check_output(["git", "-C", str(root), *args], input=data, env=env)


def resolve(root, ref):
    return git(root, "rev-parse", "--verify", f"{ref}^{{commit}}").decode().strip()


def ancestor(root, older, newer):
    return subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", older, newer],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def entries(root, ref):
    result = {}
    for record in git(root, "ls-tree", "-rz", ref).split(b"\0"):
        if record:
            meta, path = record.split(b"\t", 1)
            mode, kind, oid = meta.decode().split()
            result[path.decode()] = (mode, kind, oid)
    return result


def allowed(path):
    p = PurePosixPath(path)
    if path in PUBLIC_FILES:
        return True
    if "__pycache__" in p.parts or any(part.startswith(".") for part in p.parts):
        return False
    return ((p.parts[0] in {"src", "scripts", "tests"} and p.suffix == ".py")
            or (path == "src/goodsai/baseline.json")
            or (path.startswith("src/goodsai/examples/synthetic/") and p.suffix in {".json", ".jsonl"})
            or (path.startswith("tests/fixtures/") and p.suffix in {".json", ".jsonl"}))


def rewrite_links(content, path, published, tracked, source, origin_path=None):
    """Keep references to development evidence usable, without copying its files."""
    def replace(match):
        target = match[2]
        url = urlsplit(target)
        if url.scheme or url.netloc or not url.path or url.path.startswith("/"):
            return match[0]
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(origin_path or path), unquote(url.path)))
        if resolved in published:
            if origin_path:
                relative = posixpath.relpath(resolved, posixpath.dirname(path) or ".")
                suffix = ("?" + url.query if url.query else "") + ("#" + url.fragment if url.fragment else "")
                return match[1] + quote(relative) + suffix + match[3]
            return match[0]
        if resolved in tracked:
            suffix = ("?" + url.query if url.query else "") + ("#" + url.fragment if url.fragment else "")
            return match[1] + f"{SOURCE_REPOSITORY}/blob/{source}/{quote(resolved)}" + suffix + match[3]
        return match[0]
    return LINK.sub(replace, content)


def submission_files(root, source):
    tracked = entries(root, source)
    selected = {name for name in tracked if allowed(name)}
    if not {README_SOURCE, "pyproject.toml", "src/goodsai/cli.py", "docs/QUICKSTART.md"} <= selected:
        raise PublicationError("Submission is missing its README, package, CLI or quickstart")
    published = selected | {"README.md", MANIFEST}
    result = {}
    for name in sorted(selected):
        mode, kind, oid = tracked[name]
        if kind != "blob" or mode not in {"100644", "100755"}:
            raise PublicationError(f"Unsupported source entry (symlink/submodule): {name}")
        data = git(root, "cat-file", "blob", oid)
        if name.endswith(".md"):
            data = rewrite_links(data.decode("utf-8"), name, published, tracked, source).encode("utf-8")
        result[name] = (mode, data)
        if name == README_SOURCE:
            # Retain the template alongside the publisher for reproducible exports,
            # and rebase its relative links for the root README.
            result["README.md"] = (mode, rewrite_links(data.decode("utf-8"), "README.md", published,
                                                     tracked, source, origin_path=README_SOURCE).encode("utf-8"))
    manifest = {
        "format_version": 1,
        "source_repository": SOURCE_REPOSITORY,
        "source_sha": source,
        "files_sha256": {name: hashlib.sha256(data).hexdigest() for name, (_, data) in sorted(result.items())},
    }
    result[MANIFEST] = ("100644", (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode())
    return result


def validate_parent(root, parent, source):
    if ancestor(root, parent, source):
        return  # One-time migration from the former exact mirror; preserve history.
    tracked = entries(root, parent)
    if MANIFEST not in tracked:
        raise PublicationError("Unrecognized Gitea history; reconcile it in GitHub before publishing")
    try:
        manifest = json.loads(git(root, "show", f"{parent}:{MANIFEST}"))
        previous = manifest["source_sha"]
        if (manifest["format_version"] != 1 or manifest["source_repository"] != SOURCE_REPOSITORY
                or not isinstance(previous, str) or not SHA.fullmatch(previous)
                or not ancestor(root, previous, source)):
            raise PublicationError("Gitea source is unrelated or newer; refusing a stale publication")
        actual = {name: hashlib.sha256(git(root, "cat-file", "blob", meta[2])).hexdigest()
                  for name, meta in tracked.items() if name != MANIFEST and meta[1] == "blob"}
        if (actual != manifest["files_sha256"] or len(tracked) != len(actual) + 1
                or any(meta[0] not in {"100644", "100755"} for meta in tracked.values())):
            raise PublicationError("Gitea files differ from their manifest; reconcile manual changes first")
        # The marker must have been written by the publisher commit itself.
        changed = git(root, "diff-tree", "--root", "--no-commit-id", "--name-only", "-r", parent).decode().splitlines()
        if MANIFEST not in changed:
            raise PublicationError("Gitea contains a manual commit after publication")
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise PublicationError("Invalid Gitea submission manifest") from error


def prepare(root, source, parent):
    source, parent = resolve(root, source), resolve(root, parent)
    validate_parent(root, parent, source)
    files = submission_files(root, source)
    with tempfile.TemporaryDirectory(prefix="goodsai-submission-") as folder:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(folder) / "index"))
        git(root, "read-tree", "--empty", env=env)
        for name, (mode, data) in sorted(files.items()):
            oid = git(root, "hash-object", "-w", "--stdin", data=data).decode().strip()
            git(root, "update-index", "--add", "--cacheinfo", f"{mode},{oid},{name}", env=env)
        tree = git(root, "write-tree", env=env).decode().strip()
    if tree == git(root, "rev-parse", f"{parent}^{{tree}}").decode().strip():
        commit = parent
    else:
        identity = dict(os.environ, GIT_AUTHOR_NAME="GoodsAI release", GIT_AUTHOR_EMAIL="release@goodsai.invalid",
                        GIT_COMMITTER_NAME="GoodsAI release", GIT_COMMITTER_EMAIL="release@goodsai.invalid")
        commit = git(root, "commit-tree", tree, "-p", parent,
                     data=f"Publish submission from GitHub {source}\n".encode(), env=identity).decode().strip()
    return {"source_sha": source, "previous_gitea_sha": parent, "gitea_sha": commit,
            "tree_sha": tree, "file_count": len(files), "changed": commit != parent}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--remote", default="gitea")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    # Fetch immediately before preparation. A concurrent remote change makes the
    # ordinary push fail; no force, source-history merge or automatic retry.
    git(ROOT, "fetch", "--no-tags", args.remote, "main")
    result = prepare(ROOT, args.source, "FETCH_HEAD")
    git(ROOT, "push", args.remote, f"{result['gitea_sha']}:refs/heads/main")
    remote_sha = git(ROOT, "ls-remote", args.remote, "refs/heads/main").decode().split()[0]
    if remote_sha != result["gitea_sha"]:
        raise PublicationError("Gitea main changed during verification")
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as stream:
            stream.write(f"### Submission published\n\nGitHub: `{result['source_sha']}`\n\n"
                         f"Gitea: `{result['gitea_sha']}`\n\nFiles: {result['file_count']}\n")


if __name__ == "__main__":
    main()

"""Local-file publication: OS locks, unique staging, and recoverable prediction pairs."""
from contextlib import contextmanager, ExitStack
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile


class OutputBusyError(ValueError):
    """Another cooperating process owns the destination."""


def _sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _sync_file(path: Path):
    # Windows _commit needs a writable descriptor even when no bytes are changed.
    with path.open("r+b") as stream:
        os.fsync(stream.fileno())


def _sync_directory(path: Path):
    if os.name != "nt":
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


@contextmanager
def output_lock(path: Path):
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Never unlink a lock file: replacing its inode could create two independent locks.
    with path.with_name("." + path.name + ".goodsai.lock").open("a+b") as lock:
        try:
            if os.name == "nt":
                import msvcrt
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                raise OutputBusyError(f"Output is busy: {path.name}; retry after the other process finishes") from exc
            raise
        try:
            yield
        finally:
            if os.name == "nt":
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


@contextmanager
def _pair_lock(output: Path, manifest: Path):
    with ExitStack() as stack:
        for path in sorted({output.resolve(), manifest.resolve()}, key=lambda p: os.path.normcase(str(p))):
            stack.enter_context(output_lock(path))
        yield


@contextmanager
def _atomic_text(path: Path):
    # Caller owns the destination lock (or the private transaction directory).
    prefix = "." + path.name + ".goodsai-"
    for old in path.parent.iterdir():
        if old.name.startswith(prefix) and old.name.endswith(".tmp") and not old.is_dir():
            old.unlink()  # Reserved temp namespace; no other writer owns this destination.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         prefix=prefix, suffix=".tmp", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            yield stream
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _sync_directory(path.parent)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@contextmanager
def atomic_text(path: Path):
    path = path.resolve()
    with output_lock(path), _atomic_text(path) as stream:
        yield stream


def _journal_path(manifest: Path) -> Path:
    return manifest.with_name("." + manifest.name + ".goodsai-transaction.json")


def _write_journal(path: Path, record: dict):
    with _atomic_text(path) as stream:
        json.dump(record, stream, allow_nan=False)
        stream.write("\n")


def _transaction_directory(parent: Path, name: str) -> Path:
    if not isinstance(name, str) or not re.fullmatch(r"\.goodsai-txn-[a-zA-Z0-9_-]+", name):
        raise ValueError("Invalid prediction transaction directory")
    path = parent / name
    if path.is_symlink() or path.resolve().parent != parent.resolve():
        raise ValueError("Prediction transaction escaped its output directory")
    return path


def _cleanup(parent: Path, directory: Path):
    # Validate the absolute recursive-delete target before touching a private staging directory.
    directory = _transaction_directory(parent, directory.name)
    if directory.exists():
        shutil.rmtree(directory)


def _recover(output: Path, manifest: Path):
    journal = _journal_path(manifest)
    if not journal.exists():
        return
    try:
        record = json.loads(journal.read_text(encoding="utf-8"))
        if (record["version"] != 1 or record["output"] != output.name or record["manifest"] != manifest.name
                or record["phase"] not in {"prepared", "committed"}
                or len(record["old_sha256"]) != 2 or len(record["new_sha256"]) != 2):
            raise ValueError("Invalid or conflicting prediction transaction")
        directory = _transaction_directory(output.parent, record["directory"])
        targets = [output, manifest]
        if record["phase"] == "prepared":
            # Validate both backups before rolling back either target. Keep backups
            # intact so recovery can itself be interrupted and safely repeated.
            for i, checksum in enumerate(record["old_sha256"]):
                if checksum is not None and _sha(directory / f"old-{i}") != checksum:
                    raise ValueError("Prediction recovery backup checksum mismatch")
            for i, (target, checksum) in enumerate(zip(targets, record["old_sha256"])):
                if checksum is None:
                    target.unlink(missing_ok=True)
                else:
                    restore = directory / f"restore-{i}"
                    shutil.copyfile(directory / f"old-{i}", restore)
                    _sync_file(restore)
                    os.replace(restore, target)
        else:
            if any(_sha(p) != checksum for p, checksum in zip(targets, record["new_sha256"])):
                raise ValueError("Committed prediction pair checksum mismatch")
        _sync_directory(output.parent)
        journal.unlink()
        _sync_directory(output.parent)
        _cleanup(output.parent, directory)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError(f"Prediction recovery failed for {output.name}; preserve journal/backups for diagnosis") from exc


def _publish(output: Path, manifest: Path, directory: Path):
    targets = [output, manifest]
    staged = [directory / "data.new", directory / "manifest.new"]
    for path in staged:
        _sync_file(path)
    checksums = [_sha(path) for path in staged]
    if json.loads(staged[1].read_text(encoding="utf-8")).get("output_sha256") != checksums[0]:
        raise ValueError("Staged prediction manifest checksum mismatch")
    old = []
    for i, target in enumerate(targets):
        old.append(_sha(target) if target.exists() else None)
        if target.exists():
            # Prefer a hard link; copying is a fallback on filesystems that disallow it.
            try:
                os.link(target, directory / f"old-{i}")
            except OSError:
                shutil.copyfile(target, directory / f"old-{i}")
            _sync_file(directory / f"old-{i}")
    _sync_directory(directory)
    record = {"version": 1, "phase": "prepared", "output": output.name, "manifest": manifest.name,
              "directory": directory.name, "old_sha256": old, "new_sha256": checksums}
    journal = _journal_path(manifest)
    _write_journal(journal, record)
    try:
        os.replace(staged[0], output)
        os.replace(staged[1], manifest)
        _sync_directory(output.parent)
        record["phase"] = "committed"
        _write_journal(journal, record)
    except BaseException:
        _recover(output, manifest)
        raise
    _recover(output, manifest)  # Validate the committed pair, then retire journal/backups.


@contextmanager
def staged_prediction_pair(output: Path):
    output = output.resolve()
    manifest = output.with_suffix(".manifest.json")
    with _pair_lock(output, manifest):
        _recover(output, manifest)
        directory = Path(tempfile.mkdtemp(prefix=".goodsai-txn-", dir=output.parent))
        try:
            yield directory / "data.new", directory / "manifest.new"
            _publish(output, manifest, directory)
        finally:
            if not _journal_path(manifest).exists():
                _cleanup(output.parent, directory)


@contextmanager
def prediction_snapshot(output: Path):
    """Recover and verify a pair, keeping writers out until the reader is done."""
    output = output.resolve()
    manifest = output.with_suffix(".manifest.json")
    with _pair_lock(output, manifest):
        _recover(output, manifest)
        if manifest.exists():
            record = json.loads(manifest.read_text(encoding="utf-8"))
            if not isinstance(record, dict) or record.get("output_sha256") != _sha(output):
                raise ValueError("Prediction manifest checksum mismatch")
        yield output


class FilePredictionSink:
    """Default sink adapter; retains local-FS locks, recovery and atomic pair publication."""
    def stage(self, output: Path):
        return staged_prediction_pair(output)

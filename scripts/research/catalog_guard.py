"""Research-only checks; a digest/allowlist is not authentication or a sandbox."""
from contextlib import contextmanager
import hashlib
import os
import re

ALLOWED = {"PROTO", "FRAME", "EMPTY_DICT", "MEMOIZE", "SHORT_BINUNICODE",
           "BINUNICODE", "BINUNICODE8", "MARK", "EMPTY_LIST", "SETITEMS",
           "SETITEM", "APPENDS", "APPEND", "BINGET", "LONG_BINGET", "NONE",
           "NEWTRUE", "NEWFALSE", "BININT", "BININT1", "BININT2", "LONG1",
           "BINFLOAT", "STOP"}


def validate_scan(scan):
    if not isinstance(scan, dict) or not isinstance(scan.get("source_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", scan["source_sha256"]):
        raise ValueError("Opcode report needs a SHA-256 fingerprint")
    opcodes = scan.get("opcodes")
    if not isinstance(opcodes, dict) or not opcodes or set(opcodes) - ALLOWED:
        raise ValueError("Opcode report contains unsupported pickle instructions")
    if any(type(count) is not int or count <= 0 for count in opcodes.values()):
        raise ValueError("Invalid opcode counts")
    entries, references = scan.get("memo_entries"), scan.get("referenced_indices")
    if type(entries) is not int or entries < 0 or not isinstance(references, list):
        raise ValueError("Invalid pickle memo metadata")
    if any(type(index) is not int or not 0 <= index < entries for index in references) or len(set(references)) != len(references):
        raise ValueError("Invalid pickle memo references")


@contextmanager
def verified_catalog(path, scan):
    """Hash, read and recheck one file descriptor; require a quiescent source."""
    validate_scan(scan)
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        if hashlib.file_digest(stream, "sha256").hexdigest() != scan["source_sha256"]:
            raise ValueError("Pickle changed since opcode inspection")
        stream.seek(0)
        yield stream
        stream.seek(0)
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
        after = os.fstat(stream.fileno())
        current = os.stat(path)
        if (checksum != scan["source_sha256"] or before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns
                or (before.st_dev, before.st_ino) != (current.st_dev, current.st_ino)):
            raise ValueError("Pickle changed during profiling; discard staged outputs")

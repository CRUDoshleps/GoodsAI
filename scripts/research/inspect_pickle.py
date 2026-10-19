"""Inspect pickle opcodes without executing them; input is always read-only."""
import argparse
import collections
import json
import hashlib
import pickletools
import time
from pathlib import Path
import sys

from goodsai.storage import atomic_text
from goodsai.diagnostics import failure_message
from goodsai.data import check_output


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    check_output(args.output, args.input)
    with atomic_text(args.output) as destination:
        if args.output.exists() or args.output.is_symlink():
            raise FileExistsError("Opcode report already exists; choose a new output")
        result = inspect(args.input)
        json.dump(result, destination, allow_nan=False)
    print(json.dumps({k: v for k, v in result.items() if k != "referenced_indices"}))


def inspect(path):
    counts = collections.Counter()
    refs = set()
    memo_count = 0
    opcode_count = 0
    start = time.monotonic()
    with path.open("rb") as stream:
        for opcode, value, position in pickletools.genops(stream):
            counts[opcode.name] += 1
            opcode_count += 1
            if opcode.name in {"BINGET", "LONG_BINGET", "GET"}:
                refs.add(value)
            elif opcode.name == "MEMOIZE":
                memo_count += 1
            if opcode_count % 10_000_000 == 0:
                print(f"Scanned {position:,} bytes; referenced memo entries {len(refs):,}", flush=True)
        if stream.read(1):
            raise ValueError("Trailing data after pickle STOP")
        stream.seek(0)
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    result = {"source_sha256": digest, "opcodes": dict(counts), "memo_entries": memo_count,
              "referenced_indices": sorted(refs), "seconds": time.monotonic() - start}
    return result


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("pickle inspection: interrupted: Operation cancelled", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print("pickle inspection: " + failure_message(exc), file=sys.stderr)
        raise SystemExit(2)

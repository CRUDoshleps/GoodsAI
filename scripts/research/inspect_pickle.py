"""Inspect pickle opcodes without executing them; input is always read-only."""
import argparse
import collections
import json
import hashlib
import pickletools
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    counts = collections.Counter()
    refs = set()
    memo_count = 0
    opcode_count = 0
    start = time.monotonic()
    with args.input.open("rb") as stream:
        for opcode, value, position in pickletools.genops(stream):
            counts[opcode.name] += 1
            opcode_count += 1
            if opcode.name in {"BINGET", "LONG_BINGET", "GET"}:
                refs.add(value)
            elif opcode.name == "MEMOIZE":
                memo_count += 1
            if opcode_count % 10_000_000 == 0:
                print(f"Scanned {position:,} bytes; referenced memo entries {len(refs):,}", flush=True)
    with args.input.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    result = {"source_sha256": digest, "opcodes": dict(counts), "memo_entries": memo_count,
              "referenced_indices": sorted(refs), "seconds": time.monotonic() - start}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "referenced_indices"}))


if __name__ == "__main__":
    main()

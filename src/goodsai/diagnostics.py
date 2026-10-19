"""Operational failures never render exception text, request data or file paths."""
import re

from goodsai.storage import OutputBusyError


def failure_message(exc: Exception) -> str:
    if isinstance(exc, OutputBusyError):
        return "output_busy: Output is busy; retry after the other process finishes"
    if isinstance(exc, FileNotFoundError):
        return "file_missing: Required file is missing; check local paths"
    if isinstance(exc, PermissionError):
        return "permission_denied: Check access to the local input/output directory"
    if isinstance(exc, FileExistsError):
        return "output_exists: Output already exists; choose a new destination"
    if isinstance(exc, KeyError):
        return "invalid_metadata: Required input/configuration fields are missing"
    if isinstance(exc, ValueError):
        # Only this fully matched, bounded diagnostic may include a numeric location.
        match = re.fullmatch(r"(Blank JSONL record|Invalid JSON|JSONL object required|Duplicate SKU) at line ([0-9]{1,12})", str(exc))
        if match:
            return f"invalid_input: {match[1]} at line {match[2]}"
        return "invalid_input: Invalid input or configuration; check the schema and local files"
    if isinstance(exc, OSError):
        return "io_error: Local file operation failed; preserve artifacts for diagnosis"
    return "internal_error: Operation failed; no successful result was produced"

"""Run identity and process measurements for reproducible local CLI runs."""
import ctypes
import hashlib
import json
import platform
from pathlib import Path
import subprocess


def peak_rss_bytes() -> int | None:
    if platform.system() != "Windows":
        import resource
        size = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(size if platform.system() == "Darwin" else size * 1024)
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in ["peak_working_set", "working_set", "peak_paged_pool",
                                               "paged_pool", "peak_nonpaged_pool", "nonpaged_pool",
                                               "pagefile", "peak_pagefile"]]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    ok = psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb)
    return int(counters.peak_working_set) if ok else None


def identity(config: dict) -> dict:
    hashed = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        hashed.update(path.name.encode())
        hashed.update(path.read_bytes())
    code_hash = hashed.hexdigest()
    config_hash = hashlib.sha256(json.dumps(config, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], stderr=subprocess.DEVNULL).strip())
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = None, None
    return {"code_sha256": code_hash, "config_sha256": config_hash, "git_commit": commit,
            "git_dirty": dirty, "python": platform.python_version(), "platform": platform.platform(),
            "rules_version": config["rules_version"], "dictionary_version": config["dictionary_version"]}

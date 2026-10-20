"""Exact producer cache and bounded single-flight; no downstream decisions are stored."""
from concurrent.futures import Future, TimeoutError
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import os
import tempfile
import threading
import time

VERSION = 2


class ExactCache:
    def __init__(self, root, ttl_seconds=3600, clock=time.time):
        self.root, self.ttl_seconds, self.clock = Path(root), ttl_seconds, clock

    def _path(self, key):
        if len(key) != 64 or any(c not in '0123456789abcdef' for c in key):
            raise ValueError('Invalid exact cache key')
        return self.root / key[:2] / (key + '.json')

    def get(self, key):
        try:
            path = self._path(key)
            if path.stat().st_size > 4 * 1024 * 1024:
                return None
            entry = json.loads(path.read_text(encoding='utf-8'))
            age = self.clock() - entry['created_at']
            proposals = entry['proposals']
            payload = json.dumps(proposals, sort_keys=True, ensure_ascii=True, allow_nan=False).encode()
            if (entry['cache_version'] != VERSION or entry['key'] != key or not isinstance(proposals, list)
                    or not 0 <= age < self.ttl_seconds or entry['sha256'] != hashlib.sha256(payload).hexdigest()):
                return None
            return entry
        except (OSError, ValueError, KeyError, TypeError, RecursionError):
            return None

    def put(self, key, proposals, usage):
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        payload = json.dumps(proposals, sort_keys=True, ensure_ascii=True, allow_nan=False).encode()
        entry = {'cache_version': VERSION, 'key': key, 'created_at': self.clock(),
                 'proposals': proposals, 'sha256': hashlib.sha256(payload).hexdigest()}
        # Usage belongs to the original provider request, never billed on replay.
        temporary = None
        try:
            with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, prefix='.tmp-', delete=False) as f:
                temporary = Path(f.name)
                json.dump(entry, f, ensure_ascii=True, allow_nan=False)
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    @contextmanager
    def flight(self, key, deadline):
        """OS lock shared by processes; unavailable storage falls back to normal inference."""
        from goodsai.storage import output_lock, OutputBusyError
        while True:
            manager = output_lock(self._path(key))
            try:
                manager.__enter__()
            except OutputBusyError:
                if time.monotonic() >= deadline:
                    raise TimeoutError('Exact cache wait deadline exceeded') from None
                time.sleep(min(.02, max(0, deadline - time.monotonic())))
                continue
            except OSError:
                yield
                return
            try:
                yield
            finally:
                manager.__exit__(None, None, None)
            return


class SingleFlight:
    def __init__(self):
        self.lock, self.running = threading.Lock(), {}

    def run(self, key, work, timeout):
        with self.lock:
            future = self.running.get(key)
            shared = future is not None
            if not shared:
                future = self.running[key] = Future()
        if shared:
            try:
                return deepcopy(future.result(timeout=timeout)), True
            except TimeoutError:
                return (None, 'llm_deadline_exceeded'), True
        try:
            value = work()
            future.set_result(deepcopy(value))
            return value, False
        except BaseException:
            # Wake waiters on cancellation/programming failure, without leaking payload.
            future.set_result((None, 'llm_leader_failed'))
            raise
        finally:
            with self.lock:
                self.running.pop(key, None)


FLIGHTS = SingleFlight()


def audit(products, config, settings):
    """No provider calls, raw text or small-group fingerprints in the output."""
    from goodsai.llm import cache_key, FORBIDDEN_SOURCE_FLAGS, has_signal
    from goodsai.verify import Extractor
    rules = Extractor(config)
    keys, eligible, blocked = set(), 0, 0
    for product in products:
        if FORBIDDEN_SOURCE_FLAGS & set(product.source_flags):
            blocked += 1
            continue
        row = rules.predict(product)
        gaps = [a['attribute'] for a in row['attributes']
                if a['reason_codes'] == ['not_found_by_rules'] and has_signal(product, a['attribute'], config)]
        if gaps:
            eligible += 1
            keys.add(cache_key(product, gaps, config, settings))
    return {'eligible_requests': eligible, 'unique_requests': len(keys), 'blocked_cards': blocked,
            'potentially_avoided_calls': eligible - len(keys), 'actual_calls': 0,
            'actually_avoided_calls': 0, 'cost': None, 'quality': None}


def main():
    import argparse
    from goodsai.contracts import Product, load_config
    from goodsai.data import read_jsonl
    from goodsai.llm import LLMSettings
    p = argparse.ArgumentParser(description='Offline exact-request audit; no model calls')
    p.add_argument('--input', required=True, type=Path)
    p.add_argument('--config')
    p.add_argument('--model', required=True)
    p.add_argument('--namespace', required=True)
    args = p.parse_args()
    print(json.dumps(audit((Product.from_dict(r) for r in read_jsonl(args.input)), load_config(args.config),
                           LLMSettings(model=args.model, cache_namespace=args.namespace))))


if __name__ == '__main__':
    main()

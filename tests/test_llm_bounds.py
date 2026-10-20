"""LLM-008: bounded bytes, time and physical attempts.

A real local HTTP server exercises the stdlib client end to end (slow, oversized,
chunked, close-delimited, invalid, 429/5xx, disconnect). Fake clocks check the
deadline arithmetic without sleeping. No external network, no paid calls.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest

from goodsai.contracts import Product, load_config, validate_prediction
from goodsai.llm import (DailyLedger, LLMExtractor, LLMSettings, OpenAICompatibleProvider, ProviderError,
                         json_depth, parse_proposals)
from test_llm import FakeProvider, PHONE, Response, answer, attrs

OK_BODY = {"model": "stub-model", "choices": [{"message": {"content": '{"attributes": []}'}}],
           "usage": {"prompt_tokens": 7, "completion_tokens": 2}}


class Stub(BaseHTTPRequestHandler):
    """Scripted gateway: each request pops the next behaviour from the server queue."""
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # Keep test output and logs free of request data.
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        server = self.server
        with server.lock:
            server.requests += 1
            kind = server.script.pop(0) if server.script else "ok"
        if kind == "slow":
            time.sleep(server.slow_seconds)
            kind = "ok"
        if kind == "disconnect":
            self.close_connection = True
            self.connection.shutdown(2)
            return
        if kind in {"429", "500", "502"}:
            body = b'{"error": "busy"}'
            self.send_response(int(kind))
            if kind == "429":
                self.send_header("Retry-After", "0")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if kind == "invalid":
            self.send_json_bytes(b"this is not json")
            return
        if kind == "big_declared":
            self.send_response(200)
            self.send_header("Content-Length", str(server.limit * 4))
            self.end_headers()
            self.wfile.write(b"{" * 1024)
            self.close_connection = True
            return
        if kind == "big_chunked":
            self.send_response(200)
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            piece = b"x" * 8192
            try:
                for _ in range(server.limit // len(piece) + 4):
                    self.wfile.write(b"%x\r\n%s\r\n" % (len(piece), piece))
                self.wfile.write(b"0\r\n\r\n")
            except OSError:
                pass  # The client stops reading after its limit; that is the point.
            return
        if kind == "big_close_delimited":
            self.close_connection = True
            self.send_response(200)
            self.send_header("Connection", "close")
            self.end_headers()
            try:
                self.wfile.write(b"[" + b"1," * server.limit + b"1]")
            except OSError:
                pass
            return
        self.send_json_bytes(json.dumps(OK_BODY).encode())

    def send_json_bytes(self, body):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class LocalGateway(unittest.TestCase):
    limit = 4096

    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
        self.server.daemon_threads = True
        self.server.handle_error = lambda *_: None  # The client hanging up early is expected here.
        self.server.lock = threading.Lock()
        self.server.script, self.server.requests = [], 0
        self.server.slow_seconds, self.server.limit = 0, self.limit
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.tmp = tempfile.TemporaryDirectory()
        self.config = load_config()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def provider(self, *script, **overrides):
        self.server.script = list(script)
        values = {"model": "m", "max_response_bytes": self.limit, "timeout_seconds": 5.0,
                  "request_deadline_seconds": 30.0}
        values.update(overrides)
        settings = LLMSettings(**values)
        url = "http://127.0.0.1:%d/v1" % self.server.server_address[1]
        return OpenAICompatibleProvider(url, "secret-key", settings, sleep=lambda _: None), settings

    def expect(self, code, *script, **overrides):
        provider, _ = self.provider(*script, **overrides)
        with self.assertRaises(ProviderError) as caught:
            provider.complete([{"role": "user", "content": "x"}], 128)
        self.assertEqual(caught.exception.code, code)
        self.assertNotIn("secret-key", repr(caught.exception))
        return caught.exception

    def test_success_through_real_socket(self):
        provider, _ = self.provider("ok")
        response = provider.complete([{"role": "user", "content": "x"}], 128)
        self.assertEqual((response.model, response.attempts, response.prompt_tokens), ("stub-model", 1, 7))

    def test_oversized_bodies_are_rejected_without_full_buffering(self):
        for kind in ["big_declared", "big_chunked", "big_close_delimited"]:
            with self.subTest(kind):
                error = self.expect("llm_response_too_large", kind)
                self.assertEqual(error.attempts, 1)  # Not retryable: a bigger body will not shrink.

    def test_invalid_json_429_5xx_and_disconnect(self):
        self.assertEqual(self.expect("llm_malformed_response", "invalid").attempts, 1)
        provider, _ = self.provider("429", "502", "ok")
        self.assertEqual(provider.complete([], 128).attempts, 3)
        self.assertEqual(self.expect("llm_network_error", "disconnect", "disconnect", "disconnect").attempts, 3)
        self.assertEqual(self.expect("llm_server_error", "500", "500", "500", max_attempts=2).attempts, 2)

    def test_slow_gateway_is_cut_by_request_deadline(self):
        self.server.slow_seconds = 1.6
        started = time.monotonic()
        error = self.expect("llm_deadline_exceeded", "slow", "slow", "slow",
                            timeout_seconds=1.0, request_deadline_seconds=1.5, max_attempts=3)
        elapsed = time.monotonic() - started
        # One timed-out attempt (1 s socket timeout) and no new attempt after the deadline.
        self.assertLess(elapsed, 2.5)
        self.assertEqual(error.attempts, 1)
        self.assertLessEqual(self.server.requests, 1)

    def test_daily_ledger_counts_physical_attempts_including_retries(self):
        ledger = Path(self.tmp.name) / "ledger.json"
        provider, settings = self.provider("500", "500", "ok", daily_max_calls=2, budget_ledger=ledger)
        extractor = LLMExtractor(self.config, provider, settings)
        row = extractor.predict(PHONE)
        validate_prediction(row, self.config, PHONE)
        report = extractor.report()
        self.assertEqual(self.server.requests, 2)  # The third attempt was never sent.
        self.assertEqual((report["calls"], report["attempts"], report["retries"]), (1, 2, 1))
        self.assertEqual(report["failures"], {"llm_daily_budget_exhausted": 1})
        self.assertEqual(report["disabled_reason"], "llm_daily_budget_exhausted")
        self.assertIn("llm_daily_budget_exhausted", attrs(row)["brand"]["reason_codes"])
        self.assertEqual(DailyLedger(ledger, 2).used(), 2)
        self.assertNotIn("Zorion", ledger.read_text(encoding="utf-8"))
        # Rule decisions are untouched by the provider failure.
        self.assertEqual(attrs(row)["storage_gb"]["value"], "256")


class FakeClock:
    def __init__(self):
        self.now = 1000.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def http_error(code, retry_after=None):
    import urllib.error
    headers = {"Retry-After": retry_after} if retry_after else {}
    return urllib.error.HTTPError("https://gateway.invalid", code, "error", headers, None)


class DeadlineArithmeticTests(unittest.TestCase):
    def provider(self, clock, events, **overrides):
        timeouts = []
        events = list(events)

        def opener(request, timeout):
            timeouts.append(timeout)
            event = events.pop(0)
            if isinstance(event, tuple):  # (seconds spent, outcome)
                clock.now += event[0]
                event = event[1]
            if isinstance(event, BaseException):
                raise event
            return Response(json.dumps(event).encode())
        settings = LLMSettings(**{"model": "m", **overrides})
        provider = OpenAICompatibleProvider("https://gw.invalid/v1", "k", settings, sleep=clock.sleep,
                                            opener=opener, clock=clock)
        return provider, timeouts

    def test_socket_timeout_never_exceeds_remaining_deadline(self):
        clock = FakeClock()
        provider, timeouts = self.provider(clock, [(50.0, TimeoutError()), (5.0, TimeoutError()), OK_BODY],
                                           timeout_seconds=60.0, request_deadline_seconds=70.0)
        response = provider.complete([], 128)
        self.assertEqual(response.attempts, 3)
        # Deadline 70 s: 60 (full), then 70-50-1 = 19, then 70-50-1-5-2 = 12.
        self.assertEqual(timeouts, [60.0, 19.0, 12.0])
        self.assertEqual(clock.sleeps, [1, 2])

    def test_backoff_that_would_cross_deadline_is_not_slept(self):
        clock = FakeClock()
        provider, timeouts = self.provider(clock, [(1.0, http_error(429, "50")), OK_BODY],
                                           request_deadline_seconds=20.0)
        with self.assertRaises(ProviderError) as caught:
            provider.complete([], 128)
        self.assertEqual((caught.exception.code, caught.exception.attempts), ("llm_deadline_exceeded", 1))
        self.assertEqual((clock.sleeps, len(timeouts)), ([], 1))

    def test_explicit_deadline_in_the_past_sends_nothing(self):
        clock = FakeClock()
        provider, timeouts = self.provider(clock, [OK_BODY])
        with self.assertRaises(ProviderError) as caught:
            provider.complete([], 128, deadline=clock.now - 1)
        self.assertEqual((caught.exception.code, caught.exception.attempts, timeouts), ("llm_deadline_exceeded", 0, []))

    def test_refused_attempt_reservation_stops_before_sending(self):
        clock = FakeClock()
        provider, timeouts = self.provider(clock, [http_error(500), OK_BODY])
        answers = iter([None, "llm_daily_budget_exhausted"])
        with self.assertRaises(ProviderError) as caught:
            provider.complete([], 128, reserve_attempt=lambda: next(answers))
        error = caught.exception
        self.assertEqual((error.code, error.fatal, error.attempts, len(timeouts)),
                         ("llm_daily_budget_exhausted", True, 1, 1))


class ExtractorBoundsTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config()

    def test_waiting_for_a_busy_slot_respects_the_deadline_and_refunds_the_call(self):
        provider = FakeProvider(AssertionError("must not be called"))
        settings = LLMSettings(model="m", concurrency=1, request_deadline_seconds=1.0)
        extractor = LLMExtractor(self.config, provider, settings)
        extractor.slots.acquire()  # Another card holds the only slot.
        try:
            started = time.monotonic()
            row = extractor.predict(PHONE)
            elapsed = time.monotonic() - started
        finally:
            extractor.slots.release()
        self.assertLess(elapsed, 2.0)
        self.assertEqual(provider.calls, 0)
        report = extractor.report()
        self.assertEqual((report["calls"], report["attempts"]), (0, 0))
        self.assertIn("llm_deadline_exceeded", attrs(row)["brand"]["reason_codes"])

    def test_legacy_provider_still_reserves_and_counts_attempts(self):
        provider = FakeProvider(answer())
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.json"
            settings = LLMSettings(model="m", daily_max_calls=1, budget_ledger=ledger)
            extractor = LLMExtractor(self.config, provider, settings)
            extractor.predict(PHONE)
            row = extractor.predict(Product("s2", "761", "Смартфон Zorion QX-901"))
            self.assertEqual(DailyLedger(ledger, 1).used(), 1)
        self.assertEqual(provider.calls, 1)
        self.assertEqual(extractor.report()["attempts"], 1)
        self.assertIn("llm_daily_budget_exhausted", attrs(row)["brand"]["reason_codes"])

    def test_proposal_count_and_depth_limits(self):
        many = json.dumps({"attributes": [{"attribute": "brand", "value": None, "quote": None}] * 5})
        with self.assertRaises(ProviderError) as caught:
            parse_proposals(many, 4)
        self.assertEqual(caught.exception.code, "llm_too_many_proposals")
        self.assertEqual(len(parse_proposals(many, 5)), 5)
        deep = '{"attributes": [' + "[" * 40 + "]" * 40 + "]}"
        with self.assertRaises(ProviderError):
            parse_proposals(deep)
        self.assertEqual(json_depth({"a": [[{"b": 1}]]}), 4)
        extractor = LLMExtractor(self.config, FakeProvider(many), LLMSettings(model="m", max_proposals=4))
        row = extractor.predict(PHONE)
        self.assertIn("llm_too_many_proposals", attrs(row)["brand"]["reason_codes"])

    def test_preflight_refusals_spend_no_call_or_attempt(self):
        for base_url, key, code in [(None, None, "llm_missing_key"),
                                    ("http://gw.example/v1", "k", "llm_endpoint_not_allowed")]:
            with self.subTest(code=code):
                settings = LLMSettings(model="m")
                provider = OpenAICompatibleProvider(base_url, key, settings, opener=self.no_network)
                extractor = LLMExtractor(self.config, provider, settings)
                row = extractor.predict(PHONE)
                report = extractor.report()
                self.assertEqual((report["calls"], report["attempts"], report["disabled_reason"]), (0, 0, code))
                self.assertIn(code, attrs(row)["brand"]["reason_codes"])

    @staticmethod
    def no_network(*_args, **_kwargs):
        raise AssertionError("network must not be used")

    def test_new_limits_are_validated(self):
        for kwargs in [{"request_deadline_seconds": 0.5}, {"request_deadline_seconds": 901},
                       {"max_response_bytes": 100}, {"max_response_bytes": 1.5}, {"max_proposals": 0}]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                LLMSettings(model="m", **kwargs)


if __name__ == "__main__":
    unittest.main()

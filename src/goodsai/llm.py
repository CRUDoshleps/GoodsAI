"""Opt-in evidence-first LLM fallback for attributes the rules did not find (LLM-003).

Rules always run first. Only attributes that ended as ``not_found_by_rules`` and
whose surface form is visible in the card (``has_signal``) are sent, in one
request per card; cards without such gaps never reach the provider. A model answer is a *proposal*: it must quote
the visible card text, the value must be derived from that quote by the same
normalizer the rules use, and the candidate must pass ``validate_candidate``.
Everything else is rejected with a reason code and counted. Accepted values are
``method="llm"``, ``decision="review"`` and a heuristic score; this module never
produces ``auto_accept``.

Provider failures (missing key, timeout, 429, 5xx, malformed JSON, exhausted
budget) never change rule decisions: the affected attributes keep ``abstain``
and receive an explicit reason code. Card text, keys and base URLs are never
written to logs or to the run manifest.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import threading
import time
from typing import Callable, Protocol
import urllib.error
import urllib.parse
import urllib.request

from goodsai.contracts import Product, validate_prediction
from goodsai.normalize import NUMBER, UNITS, model_name, number, numeric
from goodsai.rules import Candidate, bounded_alias, uncertain
from goodsai.text import visible_view
from goodsai.verify import Extractor, validate_candidate

PROMPT_VERSION = "llm-fill-v1"
DATA_POLICY = "llm-data-policy-2026-10-19"
BUDGET_TIMEZONE_OFFSET_HOURS = 3  # Daily budget resets at Moscow midnight, like the gateway quota day.
FORBIDDEN_SOURCE_FLAGS = {"test_reserved", "exposed_test", "closed_test"}
CACHE_VERSION = 1
LLM_SCORE = 0.6  # Heuristic and below rule scores: a grounded proposal, not a calibrated probability.
MAX_DESCRIPTION_CHARS = 6000
MAX_TITLE_CHARS = 1000
GENERIC_WORDS = {"смартфон", "телефон", "чайник", "электрочайник", "smartphone", "phone", "kettle"}

ATTRIBUTE_HINTS = {
    "brand": "бренд производителя товара (не бренд совместимого устройства)",
    "model": "коммерческое название модели без бренда, памяти и цвета, как написано в тексте",
    "storage_gb": "объём встроенной памяти (ПЗУ/ROM), гигабайты",
    "ram_gb": "объём оперативной памяти (ОЗУ/RAM), гигабайты",
    "screen_inches": "диагональ основного экрана, дюймы",
    "battery_mah": "ёмкость аккумулятора, мА·ч",
    "capacity_l": "объём чайника, литры",
    "power_w": "мощность нагрева, ватты",
    "color": "цвет корпуса",
}

# Grounding patterns: the number and its unit must appear inside the quote.
# Units mirror goodsai.normalize.numeric; "мА*ч" is accepted as a battery unit spelling.
UNIT_PATTERNS = {
    "storage_gb": r"GB|ГБ",
    "ram_gb": r"GB|ГБ",
    "screen_inches": r"дюйм\w*|inches?\b|[\"″]",
    "battery_mah": r"м[аa][·*\s]*ч|mAh",
    "capacity_l": r"мл|ml|литр\w*|л|L",
    "power_w": r"кВт|kW|Вт|W",
}
RETRYABLE = {"llm_rate_limited", "llm_server_error", "llm_timeout", "llm_network_error"}
PAIR = re.compile(r"(?<![\w/])(?P<ram>\d{1,3})(?:\s*(?:GB|ГБ))?\s*[/+]\s*(?P<rom>\d{2,4})\s*(?:GB|ГБ)(?!\w)", re.I)

SYSTEM_PROMPT = (
    "Ты извлекаешь характеристики товара только из переданного текста карточки. "
    "Не используй знания о товаре и не угадывай. Если характеристики нет в тексте, верни для неё value=null. "
    "Для каждого найденного значения дай quote: точный фрагмент title или description, "
    "из которого видно значение (до 120 символов, без изменений). "
    "Ответ: только JSON-объект вида "
    '{"attributes":[{"attribute":"<имя>","value":"<значение или null>","quote":"<фрагмент или null>"}]} '
    "без пояснений и без других ключей."
)


class ProviderError(Exception):
    """A provider failure with a stable reason code and no request or response text."""

    def __init__(self, code: str, *, fatal: bool = False, retry_after: float | None = None, attempts: int = 1):
        super().__init__(code)
        self.code = code
        self.fatal = fatal
        self.retry_after = retry_after
        self.attempts = attempts


@dataclass(frozen=True)
class ProviderResponse:
    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str | None = None
    attempts: int = 1


class Provider(Protocol):
    model: str

    def complete(self, messages: list[dict], max_tokens: int) -> ProviderResponse: ...


@dataclass(frozen=True)
class LLMSettings:
    model: str
    max_calls: int = 100
    timeout_seconds: float = 60.0
    max_attempts: int = 3
    max_tokens: int = 2048
    concurrency: int = 2
    circuit_breaker: int = 5
    price_input_per_1k: float | None = None
    price_output_per_1k: float | None = None
    json_mode: bool = False
    cache_dir: Path | None = None
    daily_max_calls: int = 300
    budget_ledger: Path | None = None

    def __post_init__(self):
        if not isinstance(self.model, str) or not self.model.strip():
            raise ValueError("LLM model name is required")
        if type(self.max_calls) is not int or self.max_calls < 0:
            raise ValueError("LLM call budget must be a non-negative integer")
        if type(self.daily_max_calls) is not int or self.daily_max_calls < 0:
            raise ValueError("LLM daily budget must be a non-negative integer")
        if type(self.max_attempts) is not int or not 1 <= self.max_attempts <= 5:
            raise ValueError("LLM attempts must be between 1 and 5")
        if type(self.concurrency) is not int or not 1 <= self.concurrency <= 8:
            raise ValueError("LLM concurrency must be between 1 and 8")
        if not 1 <= self.timeout_seconds <= 300 or not 64 <= self.max_tokens <= 8192:
            raise ValueError("LLM timeout or token limit outside supported range")
        for price in (self.price_input_per_1k, self.price_output_per_1k):
            if price is not None and (not math.isfinite(price) or price < 0):
                raise ValueError("LLM price must be a finite non-negative number")

    def identity(self) -> dict:
        """Settings that change answers or accounting; no secrets, no URLs."""
        return {"prompt_version": PROMPT_VERSION, "model": self.model, "temperature": 0,
                "max_tokens": self.max_tokens, "json_mode": self.json_mode,
                "max_calls": self.max_calls, "daily_max_calls": self.daily_max_calls,
                "max_attempts": self.max_attempts, "data_policy": DATA_POLICY}


class OpenAICompatibleProvider:
    """Minimal stdlib client for ``POST {base}/chat/completions``.

    Structured output is validated client-side; ``json_mode`` only asks the
    gateway for ``response_format=json_object`` and is not constrained decoding.
    """

    def __init__(self, base_url: str | None, api_key: str | None, settings: LLMSettings,
                 sleep: Callable[[float], None] = time.sleep, opener=urllib.request.urlopen):
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.model = settings.model
        self.settings = settings
        self.sleep = sleep
        self.opener = opener

    def _request(self, body: bytes) -> dict:
        request = urllib.request.Request(
            self.base_url + "/chat/completions", data=body, method="POST",
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + self.api_key})
        try:
            with self.opener(request, timeout=self.settings.timeout_seconds) as response:
                payload = response.read()
        except urllib.error.HTTPError as exc:
            retry_after = None
            try:
                retry_after = float(exc.headers.get("Retry-After")) if exc.headers else None
            except (TypeError, ValueError):
                retry_after = None
            if exc.code in {401, 403}:
                raise ProviderError("llm_auth_failed", fatal=True) from None
            if exc.code == 429:
                raise ProviderError("llm_rate_limited", retry_after=retry_after) from None
            if exc.code >= 500:
                raise ProviderError("llm_server_error", retry_after=retry_after) from None
            raise ProviderError("llm_http_error") from None
        except TimeoutError:
            raise ProviderError("llm_timeout") from None
        except urllib.error.URLError as exc:
            if isinstance(getattr(exc, "reason", None), TimeoutError):
                raise ProviderError("llm_timeout") from None
            raise ProviderError("llm_network_error") from None
        except OSError:
            raise ProviderError("llm_network_error") from None
        try:
            return json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise ProviderError("llm_malformed_response") from None

    def complete(self, messages: list[dict], max_tokens: int) -> ProviderResponse:
        if not self.base_url or not self.api_key:
            raise ProviderError("llm_missing_key", fatal=True)
        if not endpoint_allowed(self.base_url):
            raise ProviderError("llm_endpoint_not_allowed", fatal=True)
        body = {"model": self.model, "messages": messages, "temperature": 0, "max_tokens": max_tokens}
        if self.settings.json_mode:
            body["response_format"] = {"type": "json_object"}
        encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
        last = None
        for attempt in range(1, self.settings.max_attempts + 1):
            if last is not None:
                delay = last.retry_after if last.retry_after is not None else 2 ** (attempt - 2)
                self.sleep(min(max(delay, 0.0), 30.0))
            try:
                data = self._request(encoded)
            except ProviderError as exc:
                exc.attempts = attempt
                if exc.fatal or exc.code not in RETRYABLE:
                    raise
                last = exc
                continue
            try:
                message = data["choices"][0]["message"]
                content = message.get("content")
                usage = data.get("usage") or {}
                prompt_tokens = int(usage.get("prompt_tokens") or 0)
                completion_tokens = int(usage.get("completion_tokens") or 0)
            except (KeyError, IndexError, TypeError, ValueError, AttributeError):
                raise ProviderError("llm_malformed_response", attempts=attempt) from None
            if not isinstance(content, str):
                raise ProviderError("llm_malformed_response", attempts=attempt)
            return ProviderResponse(content, prompt_tokens, completion_tokens, data.get("model"), attempt)
        raise last if last is not None else ProviderError("llm_network_error")


def endpoint_allowed(base_url: str) -> bool:
    """Card text leaves the machine only over TLS; plain HTTP is allowed for a local gateway."""
    parsed = urllib.parse.urlsplit(base_url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment or not parsed.hostname:
        return False
    if parsed.scheme == "https":
        return True
    return parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}


class DailyLedger:
    """Calls per local day shared by every run that points at the same file.

    The read-increment-write happens under the same OS lock the prediction writer
    uses, so parallel runs cannot overspend. Any ledger error fails closed.
    """

    def __init__(self, path: Path, limit: int, clock: Callable[[], float] = time.time):
        self.path = Path(path)
        self.limit = limit
        self.clock = clock

    def today(self) -> str:
        return time.strftime("%Y-%m-%d", time.gmtime(self.clock() + BUDGET_TIMEZONE_OFFSET_HOURS * 3600))

    def used(self) -> int:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return 0
        count = data.get(self.today(), 0) if isinstance(data, dict) else None
        if type(count) is not int or count < 0:
            raise ValueError("Corrupted LLM budget ledger")
        return count

    def reserve(self) -> str | None:
        from goodsai.storage import output_lock
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with output_lock(self.path):
                data = {}
                if self.path.exists():
                    data = json.loads(self.path.read_text(encoding="utf-8"))
                    if not isinstance(data, dict):
                        raise ValueError("Corrupted LLM budget ledger")
                used = self.used()
                if used >= self.limit:
                    return "llm_daily_budget_exhausted"
                data = {day: n for day, n in data.items() if type(n) is int}
                data[self.today()] = used + 1
                temporary = self.path.with_name("." + self.path.name + ".tmp")
                temporary.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
                os.replace(temporary, self.path)
        except (OSError, ValueError):
            return "llm_budget_ledger_unavailable"
        return None


def provider_from_env(settings: LLMSettings) -> OpenAICompatibleProvider:
    """Endpoint and key come only from the environment, never from files or CLI arguments."""
    return OpenAICompatibleProvider(os.environ.get("GOODSAI_LLM_BASE_URL"),
                                    os.environ.get("GOODSAI_LLM_API_KEY"), settings)


class ExactCache:
    """Local exact-request cache. A hit is re-grounded and re-verified like a fresh answer.

    Entries hold the parsed proposals (they quote card text), so the directory must
    stay outside Git, like ``outputs/``. Unreadable or mismatching entries are misses.
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.root / key[:2] / (key + ".json")

    def get(self, key: str) -> dict | None:
        try:
            entry = json.loads(self._path(key).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(entry, dict) or entry.get("cache_version") != CACHE_VERSION or entry.get("key") != key:
            return None
        if not isinstance(entry.get("proposals"), list):
            return None
        return entry

    def put(self, key: str, proposals: list, usage: dict) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = {"cache_version": CACHE_VERSION, "key": key, "proposals": proposals, "usage": usage}
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=".tmp-",
                                         suffix=".json", delete=False) as stream:
            json.dump(entry, stream, ensure_ascii=False)
            temporary = Path(stream.name)
        os.replace(temporary, path)


@dataclass
class LLMStats:
    """Run accounting for the manifest. Counts only; no texts."""
    cards_seen: int = 0
    cards_routed: int = 0
    cards_without_gap: int = 0
    cards_skipped_no_signal: int = 0
    cards_blocked_by_policy: int = 0
    attributes_skipped_no_signal: int = 0
    calls: int = 0
    retries: int = 0
    cache_hits: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    attributes_requested: int = 0
    proposals: int = 0
    accepted: int = 0
    seconds: float = 0.0
    rejected: Counter = field(default_factory=Counter)
    failures: Counter = field(default_factory=Counter)
    provider_models: Counter = field(default_factory=Counter)
    accepted_by_attribute: Counter = field(default_factory=Counter)

    def report(self, settings: LLMSettings) -> dict:
        priced = settings.price_input_per_1k is not None and settings.price_output_per_1k is not None
        cost = (self.prompt_tokens / 1000 * settings.price_input_per_1k
                + self.completion_tokens / 1000 * settings.price_output_per_1k) if priced else None
        return {"enabled": True, **settings.identity(), "cards_seen": self.cards_seen,
                "cards_routed": self.cards_routed, "cards_without_gap": self.cards_without_gap,
                "cards_skipped_no_signal": self.cards_skipped_no_signal,
                "cards_blocked_by_policy": self.cards_blocked_by_policy,
                "attributes_skipped_no_signal": self.attributes_skipped_no_signal,
                "calls": self.calls, "retries": self.retries, "cache_hits": self.cache_hits,
                "prompt_tokens": self.prompt_tokens, "completion_tokens": self.completion_tokens,
                "cost": cost, "cost_status": "priced" if priced else "n/a_price_unknown",
                "attributes_requested": self.attributes_requested, "proposals": self.proposals,
                "accepted": self.accepted, "accepted_by_attribute": dict(self.accepted_by_attribute),
                "rejected": dict(self.rejected), "failures": dict(self.failures),
                "provider_models": dict(self.provider_models),
                "provider_seconds": round(self.seconds, 3)}


def build_messages(product: Product, attributes: list[str], config: dict) -> list[dict]:
    title = visible_view(product.title)[0][:MAX_TITLE_CHARS]
    description = visible_view(product.description)[0][:MAX_DESCRIPTION_CHARS] if product.description else None
    requested = []
    for attr in attributes:
        item = {"attribute": attr, "meaning": ATTRIBUTE_HINTS.get(attr, attr)}
        if attr == "color":
            item["allowed_values"] = sorted(config.get("colors", {}))
        if attr in UNITS:
            item["unit"] = UNITS[attr]
        requested.append(item)
    user = {"category_id": product.category_id, "title": title, "description": description,
            "requested_attributes": requested}
    return [{"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(user, ensure_ascii=False)}]


def cache_key(product: Product, attributes: list[str], config: dict, settings: LLMSettings) -> str:
    material = {"cache_version": CACHE_VERSION, "messages": build_messages(product, attributes, config),
                "settings": {k: v for k, v in settings.identity().items() if k not in {"max_calls", "max_attempts"}},
                "config_sha256": hashlib.sha256(json.dumps(config, sort_keys=True, ensure_ascii=False).encode()).hexdigest()}
    return hashlib.sha256(json.dumps(material, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _reject_constant(_):
    raise ValueError("Non-JSON number")


def parse_proposals(content: str) -> list:
    """Strict client-side structure check; markdown fences are the only tolerated wrapper."""
    text = content.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    try:
        data = json.loads(text, parse_constant=_reject_constant)
    except (ValueError, RecursionError):
        raise ProviderError("llm_malformed_json") from None
    if not isinstance(data, dict) or set(data) != {"attributes"} or not isinstance(data["attributes"], list):
        raise ProviderError("llm_malformed_json")
    return data["attributes"]


def _quote_pattern(quote: str) -> re.Pattern:
    """The quote's own words in order; only whitespace runs may differ."""
    return re.compile(r"\s+".join(re.escape(word) for word in quote.split()))


def _locate_quote(product: Product, quote: str):
    """Exact words of the quote in visible title first, then description."""
    for field_name in ("title", "description"):
        source = getattr(product, field_name)
        if not source:
            continue
        text, positions = visible_view(source)
        match = _quote_pattern(quote).search(text)
        if match:
            return field_name, source, text, positions, match.start(), match.end()
    return None


def _raw_span(positions, start: int, end: int):
    mapping = positions[start:end]
    if not mapping or mapping[0] is None or mapping[-1] is None or any(p is None for p in mapping):
        return None
    return mapping[0][0], mapping[-1][1]


def _numeric_span(attr: str, text: str, qs: int, qe: int, wanted: Decimal):
    window = text[qs:qe]
    if attr in {"ram_gb", "storage_gb"}:
        for m in PAIR.finditer(window):
            raw = m["ram"] if attr == "ram_gb" else m["rom"]
            if number(raw) == wanted:
                return qs + m.start(), qs + m.end(), numeric(attr, raw, "GB")
    pattern = re.compile(rf"(?<![\w.,])(?P<n>{NUMBER})\s*(?P<u>{UNIT_PATTERNS[attr]})(?!\w)", re.I)
    for m in pattern.finditer(window):
        try:
            value = numeric(attr, m["n"], m["u"])
        except ValueError:
            continue
        if Decimal(value) == wanted:
            return qs + m.start(), qs + m.end(), value
    return None


def _word_span(text: str, qs: int, qe: int, needle: str):
    """First whole-word occurrence of the needle that lies inside the quoted region."""
    for m in re.finditer(bounded_alias(needle), text, re.I):
        if m.start() >= qs and m.end() <= qe:
            return m.start(), m.end()
    return None


def ground(product: Product, attr: str, value, quote, config: dict) -> tuple[Candidate | None, str | None]:
    """Turn one proposal into a verified Candidate, or return a rejection reason code."""
    if value is None:
        return None, None
    if not isinstance(value, (str, int, float)) or isinstance(value, bool) or not isinstance(quote, str):
        return None, "llm_bad_types"
    value = str(value).strip()
    quote = quote.strip()
    if not value or not quote or len(quote) > 400:
        return None, "llm_bad_types"
    located = _locate_quote(product, quote)
    if not located:
        return None, "llm_quote_not_found"
    field_name, source, text, positions, qs, qe = located
    canonical = None
    if attr in UNITS:
        try:
            wanted = number(re.sub(r"[^\d.,\s  ]", "", value).strip() or value)
        except ValueError:
            return None, "llm_value_not_in_quote"
        found = _numeric_span(attr, text, qs, qe, wanted)
        if not found:
            return None, "llm_value_not_in_quote"
        start, end, canonical = found
    elif attr == "color":
        options = [c for c, aliases in config.get("colors", {}).items()
                   if c.casefold() == value.casefold() or any(a.casefold() == value.casefold() for a in aliases)]
        if not options:
            return None, "llm_value_not_in_schema"
        span = None
        for alias in sorted(config["colors"][options[0]], key=len, reverse=True):
            span = _word_span(text, qs, qe, alias)
            if span:
                break
        if not span:
            return None, "llm_value_not_in_quote"
        start, end = span
        canonical = options[0]
    elif attr == "brand":
        if value.casefold() in GENERIC_WORDS or len(value) > 60 or not re.search(r"[^\W\d_]", value):
            return None, "llm_value_not_in_schema"
        canonical = value
        needles = [value]
        for brand, aliases in config.get("brands", {}).items():
            if brand.casefold() == value.casefold() or any(a.casefold() == value.casefold() for a in aliases):
                canonical, needles = brand, sorted(set(aliases) | {brand}, key=len, reverse=True)
                break
        span = next((s for s in (_word_span(text, qs, qe, n) for n in needles) if s), None)
        if not span:
            return None, "llm_value_not_in_quote"
        start, end = span
        if field_name == "title" and re.search(r"\b(?:для|совместим\w*)\b", text[:start], re.I):
            return None, "llm_foreign_entity"
    elif attr == "model":
        span = _word_span(text, qs, qe, value)
        if not span:
            return None, "llm_value_not_in_quote"
        start, end = span
        canonical = model_name(text[start:end])
        if canonical.casefold() in GENERIC_WORDS:
            return None, "llm_value_not_in_schema"
    else:
        return None, "llm_unknown_attribute"
    if uncertain(text, start):
        return None, "llm_uncertain_context"
    raw = _raw_span(positions, start, end)
    if raw is None:
        return None, "llm_span_not_visible"
    candidate = Candidate(attr, canonical, UNITS.get(attr), field_name, raw[0], raw[1],
                          source[raw[0]:raw[1]], LLM_SCORE, "llm." + PROMPT_VERSION)
    try:
        validate_candidate(candidate, product, config["categories"][product.category_id])
    except (ValueError, KeyError):
        return None, "llm_failed_verification"
    return candidate, None


TITLE_TOKEN = re.compile(r"[^\W_][\w\-+/.]*", re.U)


def has_signal(product: Product, attr: str, config: dict) -> bool:
    """Cheap pre-router: could *any* answer for this attribute pass grounding?

    The verifier only accepts a value that is visibly present in the card, so an
    attribute whose surface form is absent cannot be filled by the model at all.
    Such gaps are not sent; this saves calls without changing what can be accepted.
    """
    texts = [visible_view(product.title)[0]]
    if product.description:
        texts.append(visible_view(product.description)[0])
    if attr in UNIT_PATTERNS:
        number_unit = re.compile(rf"(?<![\w.,]){NUMBER}\s*(?:{UNIT_PATTERNS[attr]})(?!\w)", re.I)
        if any(number_unit.search(t) for t in texts):
            return True
        return attr in {"ram_gb", "storage_gb"} and any(PAIR.search(t) for t in texts)
    if attr == "color":
        return any(re.search(bounded_alias(alias), t, re.I)
                   for aliases in config.get("colors", {}).values() for alias in aliases for t in texts)
    if attr in {"brand", "model"}:
        # Brand and model are expected in the title; a title of generic words has nothing to quote.
        tokens = [t for t in TITLE_TOKEN.findall(texts[0][:200]) if t.casefold() not in GENERIC_WORDS]
        if attr == "brand":
            return any(re.search(r"[^\W\d_]", t) for t in tokens)
        return any(re.search(r"\d", t) and re.search(r"[^\W\d_]", t) or re.fullmatch(r"[A-Za-z][\w\-]+", t)
                   for t in tokens)
    return False


class LLMExtractor:
    """Rules first; one grounded LLM request per card for unresolved attributes only."""

    def __init__(self, config: dict, provider: Provider, settings: LLMSettings):
        self.config = config
        self.rules = Extractor(config)
        self.provider = provider
        self.settings = settings
        self.cache = ExactCache(settings.cache_dir) if settings.cache_dir else None
        self.ledger = DailyLedger(settings.budget_ledger, settings.daily_max_calls) if settings.budget_ledger else None
        self.stats = LLMStats()
        self.disabled_reason: str | None = None
        self.consecutive_failures = 0
        self.lock = threading.Lock()
        self.slots = threading.BoundedSemaphore(settings.concurrency)

    def report(self) -> dict:
        with self.lock:
            report = self.stats.report(self.settings)
            report["disabled_reason"] = self.disabled_reason
            report["daily_budget"] = "ledger" if self.ledger is not None else "not_enforced"
            return report

    def _reserve_call(self) -> str | None:
        with self.lock:
            if self.disabled_reason:
                return self.disabled_reason
            if self.stats.calls >= self.settings.max_calls:
                return "llm_budget_exhausted"
            if self.ledger is not None:
                blocked = self.ledger.reserve()
                if blocked:
                    if blocked == "llm_budget_ledger_unavailable":
                        self.disabled_reason = blocked
                    return blocked
            self.stats.calls += 1
            return None

    def _record_failure(self, exc: ProviderError) -> None:
        with self.lock:
            self.stats.failures[exc.code] += 1
            self.consecutive_failures += 1
            if exc.fatal:
                self.disabled_reason = exc.code
            elif self.consecutive_failures >= self.settings.circuit_breaker:
                self.disabled_reason = "llm_circuit_open"

    def _proposals(self, product: Product, gaps: list[str]) -> tuple[list | None, str | None]:
        key = cache_key(product, gaps, self.config, self.settings) if self.cache else None
        if self.cache:
            entry = self.cache.get(key)
            if entry is not None:
                with self.lock:
                    self.stats.cache_hits += 1
                return entry["proposals"], None
        blocked = self._reserve_call()
        if blocked:
            with self.lock:
                self.stats.failures[blocked] += 1
            return None, blocked
        started = time.perf_counter()
        try:
            with self.slots:
                response = self.provider.complete(build_messages(product, gaps, self.config), self.settings.max_tokens)
        except ProviderError as exc:
            with self.lock:
                self.stats.retries += max(0, exc.attempts - 1)
            self._record_failure(exc)
            return None, exc.code
        finally:
            with self.lock:
                self.stats.seconds += time.perf_counter() - started
        with self.lock:
            self.stats.retries += max(0, response.attempts - 1)
            if isinstance(response.model, str) and len(response.model) <= 200:
                self.stats.provider_models[response.model] += 1
            self.stats.prompt_tokens += response.prompt_tokens
            self.stats.completion_tokens += response.completion_tokens
        try:
            proposals = parse_proposals(response.content)
        except ProviderError as exc:
            self._record_failure(exc)
            return None, exc.code
        with self.lock:
            self.consecutive_failures = 0
        if self.cache:
            try:
                self.cache.put(key, proposals, {"prompt_tokens": response.prompt_tokens,
                                                "completion_tokens": response.completion_tokens})
            except OSError:
                with self.lock:
                    self.stats.failures["llm_cache_write_failed"] += 1
        return proposals, None

    def predict(self, product: Product, run_id: str = "rules-llm-v0") -> dict:
        row = self.rules.predict(product, run_id)
        with self.lock:
            self.stats.cards_seen += 1
        if row["status"] != "processed":
            return row
        by_attr = {a["attribute"]: a for a in row["attributes"]}
        open_gaps = [a["attribute"] for a in row["attributes"] if a["reason_codes"] == ["not_found_by_rules"]]
        if open_gaps and FORBIDDEN_SOURCE_FLAGS & set(product.source_flags):
            # Closed test cards never leave the machine (data policy).
            for attr in open_gaps:
                by_attr[attr]["reason_codes"].append("llm_blocked_by_data_policy")
            with self.lock:
                self.stats.cards_blocked_by_policy += 1
            validate_prediction(row, self.config, product)
            return row
        if not open_gaps:
            with self.lock:
                self.stats.cards_without_gap += 1
            return row
        gaps = [attr for attr in open_gaps if has_signal(product, attr, self.config)]
        for attr in open_gaps:
            if attr not in gaps:
                by_attr[attr]["reason_codes"].append("llm_skipped_no_signal")
        with self.lock:
            self.stats.attributes_skipped_no_signal += len(open_gaps) - len(gaps)
            if not gaps:
                self.stats.cards_skipped_no_signal += 1
        if not gaps:
            validate_prediction(row, self.config, product)
            return row
        with self.lock:
            self.stats.cards_routed += 1
            self.stats.attributes_requested += len(gaps)
        proposals, failure = self._proposals(product, gaps)
        if failure:
            for attr in gaps:
                by_attr[attr]["reason_codes"].append(failure)
            validate_prediction(row, self.config, product)
            return row
        grounded: dict[str, list[Candidate]] = {attr: [] for attr in gaps}
        rejected: dict[str, list[str]] = {attr: [] for attr in gaps}
        for item in proposals:
            with self.lock:
                self.stats.proposals += 1
            if not isinstance(item, dict) or set(item) != {"attribute", "value", "quote"}:
                with self.lock:
                    self.stats.rejected["llm_unknown_field"] += 1
                continue
            attr = item["attribute"]
            if attr not in grounded:
                with self.lock:
                    self.stats.rejected["llm_unknown_attribute"] += 1
                continue
            candidate, reason = ground(product, attr, item["value"], item["quote"], self.config)
            if reason:
                rejected[attr].append(reason)
                with self.lock:
                    self.stats.rejected[reason] += 1
            elif candidate:
                grounded[attr].append(candidate)
        for attr in gaps:
            target = by_attr[attr]
            values = {(c.value, c.unit) for c in grounded[attr]}
            if len(values) > 1:
                target["reason_codes"].append("conflicting_llm_evidence")
            elif grounded[attr]:
                c = min(grounded[attr], key=lambda c: (c.field != "title", c.start))
                target.update(value=c.value, unit=c.unit, confidence=c.score, decision="review",
                              method="llm", rule_id=c.rule_id, reason_codes=[],
                              evidence={"field": c.field, "start": c.start, "end": c.end, "text": c.text})
                with self.lock:
                    self.stats.accepted += 1
                    self.stats.accepted_by_attribute[attr] += 1
            else:
                target["reason_codes"].append(rejected[attr][0] if rejected[attr] else "llm_not_found")
        validate_prediction(row, self.config, product)
        return row


TRACE_PRODUCT = {"schema_version": "0.1", "sku_id": "synthetic-llm-trace-1", "category_id": "761",
                 "title": "Смартфон Zorion QX-900 8/256GB черный",
                 "description": "Ёмкость 5000 мА*ч. Экран 6,7 дюйма.",
                 "seller_attributes": [], "source_flags": ["synthetic"]}


def synthetic_trace(extractor: "LLMExtractor") -> dict:
    """One synthetic card through the live route: candidate, verifier result and usage.

    The card is invented for this check, so it may be stored in full; no catalog text is sent.
    """
    product = Product.from_dict(TRACE_PRODUCT)
    rules = extractor.rules.predict(product, "llm-trace")
    row = extractor.predict(product, "llm-trace")
    changes = []
    for before, after in zip(rules["attributes"], row["attributes"]):
        if before != after:
            changes.append({"attribute": after["attribute"], "rules": before["reason_codes"],
                            "decision": after["decision"], "method": after["method"], "value": after["value"],
                            "evidence": after["evidence"], "reason_codes": after["reason_codes"]})
    return {"trace_version": 1, "data_policy": DATA_POLICY, "input": TRACE_PRODUCT,
            "verified_prediction": row, "llm_changes": changes, "llm": extractor.report(),
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

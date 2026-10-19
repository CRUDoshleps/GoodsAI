"""Bounded source fragments for a future selector; no attribute decisions or inference side effects."""
from dataclasses import asdict, dataclass
import hashlib
import json
import re
import unicodedata

from goodsai.contracts import Product
from goodsai.normalize import NUMBER
from goodsai.text import visible_view

ALGORITHM_VERSION = "span-index-1"
TOKEN = re.compile(r"\w+(?:[-./+]\w+)*", re.UNICODE)
NUMERIC = re.compile(rf"(?<!\w){NUMBER}(?:\s*(?:[/+]\s*{NUMBER}))?"
                     r"(?:[^\S\n]*(?:GB|ГБ|mAh|м[аa][*·⋅\s]*ч|кВт|kW|Вт|W|ml|мл|л|L|inch|дюйм\w*|[\"″]))?(?!\w)", re.I)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=True, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SpanConfig:
    max_source_chars: int = 65536
    max_spans: int = 2048
    max_window_tokens: int = 8
    max_span_chars: int = 192

    def __post_init__(self):
        bounds = {"max_source_chars": 262144, "max_spans": 20000,
                  "max_window_tokens": 16, "max_span_chars": 1024}
        for key, upper in bounds.items():
            value = getattr(self, key)
            if type(value) is not int or not 1 <= value <= upper:
                raise ValueError(f"Invalid SpanConfig {key}")


@dataclass(frozen=True)
class SpanEntry:
    span_id: str
    field: str
    start: int
    end: int
    surface: str


@dataclass(frozen=True)
class SpanIndex:
    algorithm_version: str
    source_sha256: str
    config_sha256: str
    index_id: str
    status: str
    reason_codes: tuple[str, ...]
    entries: tuple[SpanEntry, ...]

    def resolve(self, span_id: str, product: Product, config: SpanConfig | None = None) -> SpanEntry:
        """Reject IDs from another source/config, including equal quotes at other offsets."""
        config = config or SpanConfig()
        if (self.source_sha256 != source_hash(product) or self.config_sha256 != fingerprint(asdict(config))
                or self.algorithm_version != ALGORITHM_VERSION):
            raise ValueError("Span index source/config/version mismatch")
        for entry in self.entries:
            if entry.span_id == span_id:
                source = getattr(product, entry.field) or ""
                if source[entry.start:entry.end] != entry.surface:
                    raise ValueError("Span index evidence mismatch")
                return entry
        raise ValueError("Unknown span ID; no approximate lookup")


def source_hash(product):
    # Deliberately excludes SKU/category/flags: the index is a pure function of source text.
    hashed = hashlib.sha256()
    for field in ("title", "description"):
        source = getattr(product, field)
        hashed.update(field.encode("ascii"))
        if source is None:
            hashed.update(b"N;")
        else:
            hashed.update(f"S{len(source)}:".encode("ascii"))
            # Even an over-limit source gets an identity without building a second large string/map.
            for offset in range(0, len(source), 8192):
                hashed.update(source[offset:offset + 8192].encode("utf-8", errors="surrogatepass"))
    return hashed.hexdigest()


def _intervals(text, config, reasons):
    """Numeric intervals first, then bounded token windows; no all-pairs enumeration."""
    for match in NUMERIC.finditer(text):
        yield match.start(), match.end()
    tokens = []
    for match in TOKEN.finditer(text):
        end = match.end()
        while end < len(text) and unicodedata.category(text[end]).startswith("M"):
            end += 1
        tokens.append((match.start(), end))
    for i, (start, _) in enumerate(tokens):
        for j in range(i, min(i + config.max_window_tokens, len(tokens))):
            end = tokens[j][1]
            if j > i and "\n" in text[tokens[j - 1][1]:tokens[j][0]]:
                break
            if end - start > config.max_span_chars:
                reasons.add("span_length_limit")
                break
            yield start, end
        next_token = i + config.max_window_tokens
        if next_token < len(tokens) and "\n" not in text[start:tokens[next_token][0]]:
            reasons.add("window_token_limit")


def build_span_index(product: Product, config: SpanConfig | None = None) -> SpanIndex:
    config = config or SpanConfig()
    source_sha = source_hash(product)
    config_sha = fingerprint(asdict(config))
    index_id = fingerprint([ALGORITHM_VERSION, source_sha, config_sha])
    reasons = set()
    entries = []
    seen = set()
    source_chars = len(product.title) + len(product.description or "")
    if source_chars > config.max_source_chars:
        return SpanIndex(ALGORITHM_VERSION, source_sha, config_sha, index_id, "unavailable",
                         ("source_length_limit",), ())
    # Field order and numeric-before-window priority are part of the versioned algorithm.
    views = [(field, source, *visible_view(source)) for field in ("title", "description")
             if (source := getattr(product, field))]
    for field, source, text, positions in views:
        for start, end in _intervals(text, config, reasons):
            first, last = positions[start], positions[end - 1]
            if first is None or last is None or any(pos is None for pos in positions[start:end]):
                continue
            # An entity may decode to multiple characters: never index half of that entity.
            if (start and positions[start - 1] == first) or (end < len(positions) and positions[end] == last):
                continue
            raw_start, raw_end = first[0], last[1]
            if raw_end - raw_start > config.max_span_chars:
                reasons.add("span_length_limit")
                continue
            key = (field, raw_start, raw_end)
            if key in seen:
                continue
            seen.add(key)
            if len(entries) == config.max_spans:
                reasons.add("span_count_limit")
                break
            entry_id = fingerprint([index_id, *key])
            entries.append(SpanEntry(entry_id, field, raw_start, raw_end, source[raw_start:raw_end]))
        if "span_count_limit" in reasons:
            break
    if not entries:
        reasons.add("no_visible_spans")
    status = "unavailable" if not entries else "truncated" if reasons else "available"
    return SpanIndex(ALGORITHM_VERSION, source_sha, config_sha, index_id, status, tuple(sorted(reasons)), tuple(entries))

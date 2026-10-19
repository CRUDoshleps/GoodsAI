"""Conservative syntax for explicit model names; no catalogue or SKU lookup."""
import re

LETTERS = "A-Za-zА-Яа-яЁё"
TOKEN = rf"[{LETTERS}0-9]+(?:[-.][{LETTERS}0-9]+)*"
WORD = rf"[{LETTERS}]+"
CODE = rf"(?=[{LETTERS}0-9.-]*\d)[{LETTERS}][{LETTERS}0-9]*(?:[-.][{LETTERS}0-9]+)*"
IDENTIFIER = rf"(?:{CODE}|\d{{1,4}})"
NETWORK = r"(?:4G|5G|LTE)"
SUFFIX = r"(?:Pro|Ultra|Plus|Max|Lite|Mini|FE|SE|Neo)"
NAME = re.compile(rf"(?:{WORD}\s+){{0,2}}{IDENTIFIER}(?:\s+{SUFFIX}){{0,2}}(?:\s+{NETWORK})?", re.I)
KETTLE_CODE = re.compile(rf"(?<!\w)(?:{CODE}|[A-ZА-ЯЁ]{{1,6}}\s+\d{{1,6}})(?!\w)")
MARKER = re.compile(r"\b(?:модель|model)\s*[:=]\s*", re.I)
BAD_CONTEXT = re.compile(
    r"\b(?:для|совместим\w*|сравн\w*|вместо|аналог\w*|поддерж\w*|не|нет|без|"
    r"чехол\w*|кабел\w*|аккумулятор\w*|запчаст\w*|крышк\w*|подставк\w*)\b", re.I)
DESCRIPTOR = re.compile(
    r"^\s*(?:(?:восстановленный|новый|мобильный)\s+)?"
    r"(?:смартфон|телефон|электрочайник|чайник|электрический\s+чайник)\s+", re.I)
QUANTITY = re.compile(r"\d+(?:[.,]\d+)?(?:\s*[/+]\s*\d+)?\s*(?:GB|ГБ|TB|ТБ|мАч|mAh|Вт|W|кВт|л|L|дюйм\w*)(?!\w)", re.I)
STATE = re.compile(r"(?:восстановленный|рабочий|новый|б/у)\b", re.I)


class ModelRules:
    def __init__(self, config: dict):
        self.profiles = config["category_profiles"]
        # Reuse public manufacturer/color spellings only to locate boundaries.
        self.brands = sorted({a for aliases in config["brands"].values() for a in aliases}, key=len, reverse=True)
        self.phone_brands = sorted({a for name, aliases in config["brands"].items()
                                    if name not in {"GALAXY", "Galaxy Line"} for a in aliases}, key=len, reverse=True)
        # Model boundaries only: do not change the existing brand extractor.
        self.model_brands = sorted(set(self.brands) | set(config.get("model_brand_aliases", [])),
                                   key=len, reverse=True)
        self.colors = sorted({a for aliases in config["colors"].values() for a in aliases}, key=len, reverse=True)

    @staticmethod
    def prefix(text: str, aliases: list[str]):
        for alias in aliases:
            m = re.match(re.escape(alias).replace(r"\ ", r"[^\S\n]+") + r"(?!\w)", text, re.I)
            if m:
                return m
        return None

    def brand_end(self, text: str, aliases: list[str], repeated: bool = False) -> int | None:
        """Skip explicit adjacent brand tokens; Galaxy remains a phone family."""
        end = 0
        while match := self.prefix(text[end:], aliases):
            end += match.end()
            while end < len(text) and text[end].isspace():
                end += 1
            if not repeated:
                break
        return end or None

    def tail_is_boundary(self, tail: str) -> bool:
        tail = tail.strip()
        if not tail:
            return True
        # A measure starts a specifications suffix. Never infer its missing unit.
        if QUANTITY.match(tail):
            return True
        tail = tail.lstrip(",; ")
        color = self.prefix(tail, self.colors)
        if color:
            rest = tail[color.end():].strip()
            return not rest or (rest.startswith(",") and bool(STATE.fullmatch(rest[1:].strip())))
        return bool(STATE.fullmatch(tail))

    def explicit(self, category: str, text: str):
        for marker in MARKER.finditer(text):
            # Only labelled fields, never references to another product.
            line_start = max(text.rfind("\n", 0, marker.start()), text.rfind(";", 0, marker.start())) + 1
            if BAD_CONTEXT.search(text[line_start:marker.start()]):
                continue
            start = marker.end()
            stop = re.search(r"[\n;,]", text[start:])
            end = start + stop.start() if stop else len(text)
            fragment = text[start:end].rstrip()
            end = start + len(fragment)
            indices = [token for token in fragment.split() if re.search(r"\d", token)
                       and not re.fullmatch(NETWORK, token, re.I)]
            if (not fragment or BAD_CONTEXT.search(fragment) or STATE.search(fragment)
                    or len(indices) > 1
                    or not re.search(rf"[{LETTERS}]", fragment) or re.fullmatch(NETWORK, fragment, re.I)
                    or not re.fullmatch(rf"{TOKEN}(?:\s+{TOKEN}){{0,5}}", fragment)
                    or QUANTITY.search(fragment)
                    or re.search(r"\b(?:и|или|and|or)\b", fragment, re.I)
                    or any(re.search(r"(?<!\w)" + re.escape(a) + r"(?!\w)", fragment, re.I) for a in self.colors)
                    or re.search(r"\b(?:тип|type|артикул|неизвестн\w*|указан\w*)\b", fragment, re.I)):
                continue
            # Strip an explicitly repeated brand, never derive a missing brand.
            brands = self.phone_brands if self.profiles[category] == "smartphone" else self.model_brands
            brand_end = self.brand_end(fragment, brands, repeated=self.profiles[category] == "smartphone")
            if brand_end:
                start += brand_end
            if start < end:
                yield start, end, "model.labelled.v2"

    def title(self, category: str, text: str):
        if "\n" in text.strip() or BAD_CONTEXT.search(text):
            return
        descriptor = DESCRIPTOR.match(text)
        begin = descriptor.end() if descriptor else len(text) - len(text.lstrip())
        body = text[begin:]
        if self.profiles[category] == "smartphone":
            brand_end = self.brand_end(body, self.phone_brands, repeated=True)
            if brand_end is None:
                return
            begin += brand_end
            m = NAME.match(text, begin)
            if not m:
                return
            fragment = m.group()
            # An isolated number or a unit is not an explicit model name.
            if (not re.search(rf"[{LETTERS}]", fragment)
                    or QUANTITY.fullmatch(fragment) or not self.tail_is_boundary(text[m.end():])):
                return
            yield begin, m.end(), "model.phone-title.v2"
        elif self.profiles[category] == "kettle" and descriptor:
            # A manufacturer phrase followed by exactly one unambiguous index.
            matches = list(KETTLE_CODE.finditer(body))
            if len(matches) != 1:
                return
            m = matches[0]
            manufacturer = body[:m.start()].strip()
            known_brand = self.prefix(body, self.model_brands)
            if known_brand:
                # Words between an explicit maker and its index may be part of
                # the commercial model. Do not silently discard them.
                if manufacturer.casefold() != known_brand.group().strip().casefold():
                    return
            elif not re.fullmatch(rf"{WORD}(?:\s*&\s*{WORD}){{0,3}}", manufacturer):
                # An unrecognised multiword prefix could be maker + model series.
                return
            if not self.tail_is_boundary(body[m.end():]):
                return
            yield begin + m.start(), begin + m.end(), "model.kettle-title.v2"

    def spans(self, category: str, field: str, text: str):
        yield from self.explicit(category, text)
        if field == "title" and not MARKER.search(text):
            yield from self.title(category, text)

"""Category-specific span rules; all evidence comes from visible input text."""
from dataclasses import dataclass, replace
import re

from goodsai.contracts import Product
from goodsai.model_rules import ModelRules
from goodsai.normalize import NUMBER, UNITS, model_name, number, numeric
from goodsai.text import segments, visible_view


@dataclass(frozen=True)
class Candidate:
    attribute: str
    value: str
    unit: str | None
    field: str
    start: int
    end: int
    text: str
    score: float
    rule_id: str


def bounded_alias(alias: str) -> str:
    return r"(?<!\w)" + re.escape(alias) + r"(?!\w)"


def uncertain(text: str, start: int) -> bool:
    prefix = text[max(0, start - 35):start]
    return bool(re.search(r"(?:\d\s*[-–—]|\b(?:от|до|около|примерно|менее|более)|"
                          r"\b(?:не|нет|без)(?:\s+\w+){0,2})\s*$", prefix, re.I))


def context(text: str, start: int, end: int, radius: int = 45) -> str:
    return text[max(0, start - radius):min(len(text), end + radius)]


class Rules:
    def __init__(self, config: dict):
        self.config = config
        self.model_rules = ModelRules(config)
        self.aliases = {}
        for kind in ["brands", "colors"]:
            self.aliases[kind] = [(canonical, re.compile(bounded_alias(alias), re.I))
                                  for canonical, aliases in config[kind].items() for alias in aliases]
        self.patterns = {
            "memory": re.compile(rf"(?<![\w.,])(?P<n>{NUMBER})\s*(?P<u>GB|ГБ)(?!\w)", re.I),
            "screen_inches": re.compile(rf"(?<![\w.,])(?P<n>{NUMBER})\s*(?P<u>дюйм\w*|inches?\b|[\"″])", re.I),
            "battery_mah": re.compile(rf"(?<![\w.,])(?P<n>{NUMBER})\s*(?P<u>м[аa][·\s]*ч|mAh)(?!\w)", re.I),
            "capacity_l": re.compile(rf"(?<![\w.,])(?P<n>{NUMBER})\s*(?P<u>мл|ml|литр\w*|л|L)(?!\w)", re.I),
            "power_w": re.compile(rf"(?<![\w.,])(?P<n>{NUMBER})\s*(?P<u>кВт|kW|Вт|W)(?!\w)", re.I),
        }
        self.pair = re.compile(r"(?<![\w/])(?P<ram>\d{1,3})\s*[/+]\s*(?P<rom>\d{2,4})\s*(?:GB|ГБ)(?!\w)", re.I)
        self.roles = {
            "ram_gb": re.compile(r"оперативн\w*|\bОЗУ\b|\bRAM\b", re.I),
            "storage_gb": re.compile(r"встроенн\w*|постоянн\w*|\bROM\b|накопител\w*", re.I),
            "card": re.compile(r"карт\w*\s+памят\w*|micro\s*SD|SDXC|SDHC", re.I),
        }

    @staticmethod
    def make(attribute, value, field, offset, text, match, rule, score=0.8):
        return Candidate(attribute, value, UNITS.get(attribute), field,
                         offset + match.start(), offset + match.end(), match.group(), score, rule)

    def brand(self, product: Product):
        # The first explicit manufacturer in a title wins over model names such as Galaxy/Redmi.
        matches = []
        for offset, text in segments(product.title):
            for canonical, pattern in self.aliases["brands"]:
                if product.category_id == "761" and canonical == "GALAXY":
                    continue  # A kettle manufacturer, but a model family in smartphone titles.
                for m in pattern.finditer(text):
                    if uncertain(text, m.start()) or re.search(r"\b(?:для|совместим\w*)\b", text[:m.start()], re.I):
                        continue
                    if offset + m.start() < 65:
                        matches.append((offset + m.start(), -len(m.group()), canonical, offset, text, m))
        if matches:
            _, _, canonical, offset, text, m = min(matches, key=lambda x: x[:2])
            yield self.make("brand", canonical, "title", offset, text, m, "brand.explicit-title.v1", 0.85)

    def colors(self, field: str, offset: int, text: str):
        found = [(canonical, m) for canonical, pattern in self.aliases["colors"]
                 for m in pattern.finditer(text)]
        for canonical, m in found:
            if any(other.start() <= m.start() and other.end() >= m.end()
                   and other.end() - other.start() > m.end() - m.start() for _, other in found):
                continue  # Do not turn dark blue into two colors.
            prefix = text[max(0, m.start() - 20):m.start()]
            if re.search(r"(?:\w+-|\b(?:темно|тёмно|светло|ярко|бледно|dark|light)\s+)$", prefix, re.I):
                continue  # An unconfigured shade/compound is not the basic color.
            local = context(text, m.start(), m.end(), 30)
            if uncertain(text, m.start()) or re.search(r"подсветк|индикатор|упаковк|кнопк|шнур|ручк", local, re.I):
                continue
            if field == "description" and not re.search(r"цвет\w*|корпус\w*", local, re.I):
                continue
            yield self.make("color", canonical, field, offset, text, m, "color.explicit.v1", 0.75)

    def memory_role(self, text: str, start: int, end: int) -> str | None:
        found = []
        for role, pattern in self.roles.items():
            for m in pattern.finditer(text):
                distance = start - m.end() if m.end() <= start else m.start() - end
                if 0 <= distance <= 45:
                    between = text[m.end():start] if m.end() <= start else text[end:m.start()]
                    if not re.search(r"[.!?;\n]", between):
                        found.append((distance, role))
        if not found:
            return None
        found.sort()
        if len(found) > 1 and found[0][0] == found[1][0] and found[0][1] != found[1][1]:
            return "ambiguous"
        return found[0][1]

    def memory(self, field: str, offset: int, text: str):
        pairs = list(self.pair.finditer(text)) if field == "title" else []
        for m in pairs:
            if uncertain(text, m.start()):
                continue
            ram, rom = int(m["ram"]), int(m["rom"])
            if not 1 <= ram <= 64 or not 16 <= rom <= 4096 or ram >= rom:
                continue
            for attr, value in [("ram_gb", ram), ("storage_gb", rom)]:
                yield self.make(attr, str(value), field, offset, text, m, "memory.title-pair.v1", 0.8)
        for m in self.patterns["memory"].finditer(text):
            if any(p.start() <= m.start() < p.end() for p in pairs) or uncertain(text, m.start()):
                continue
            role = self.memory_role(text, m.start(), m.end())
            if role is None and field == "title" and number(m["n"]) >= 32:
                role = "storage_gb"
            if role not in {"ram_gb", "storage_gb"}:
                continue
            try:
                value = numeric(role, m["n"], m["u"])
            except ValueError:
                continue
            yield self.make(role, value, field, offset, text, m, "memory.context.v1", 0.8)

    def quantities(self, product: Product, field: str, offset: int, text: str):
        attributes = (["screen_inches", "battery_mah"] if product.category_id == "761"
                      else ["capacity_l", "power_w"])
        for attr in attributes:
            for m in self.patterns[attr].finditer(text):
                local = context(text, m.start(), m.end())
                if uncertain(text, m.start()):
                    continue
                if attr == "screen_inches":
                    if re.search(r"дополнител\w*\s+экран|развернут|развёрнут", local, re.I):
                        continue
                    if field != "title" and not re.search(r"диагонал|экран|диспле", local, re.I):
                        continue
                if attr == "battery_mah" and not re.search(r"аккумулятор|батаре", local, re.I):
                    continue
                if attr == "capacity_l":
                    if re.search(r"заварочн|чашк|стакан|упаковк", local, re.I):
                        continue
                    if field != "title" and not re.search(r"об[ъь]?ем|объём|вместим|резервуар|чайник", local, re.I):
                        continue
                if attr == "power_w":
                    if re.search(r"ожидани|дежурн|поддержани|подогрев", local, re.I):
                        continue
                    if field != "title" and not re.search(r"мощност|нагревател", local, re.I):
                        continue
                try:
                    value = numeric(attr, m["n"], m["u"])
                except ValueError:
                    continue
                yield self.make(attr, value, field, offset, text, m, attr + ".explicit.v1", 0.8)

    def models(self, product: Product, field: str, text: str):
        for start, end, rule in self.model_rules.spans(product.category_id, field, text):
            fragment = text[start:end]
            yield Candidate("model", model_name(fragment), None, field, start, end,
                            fragment, 0.8, rule)

    def candidates(self, product: Product):
        yield from self.brand(product)
        for field in ["title", "description"]:
            source = getattr(product, field) or ""
            text, positions = visible_view(source)
            found = list(self.colors(field, 0, text))
            found.extend(self.models(product, field, text))
            if product.category_id == "761":
                found.extend(self.memory(field, 0, text))
            found.extend(self.quantities(product, field, 0, text))
            for candidate in found:
                first, last = positions[candidate.start], positions[candidate.end - 1]
                if first is None or last is None:
                    continue
                yield replace(candidate, start=first[0], end=last[1], text=source[first[0]:last[1]])

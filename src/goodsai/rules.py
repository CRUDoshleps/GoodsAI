"""Category-specific span rules; all evidence comes from visible input text."""
from dataclasses import replace
import re

from goodsai.contracts import Product
from goodsai.config import default_limits
from goodsai.model_rules import ModelRules
from goodsai.normalize import NUMBER, UNITS, model_name, numeric
from goodsai.text import visible_view


from goodsai.stages import Candidate


def bounded_alias(alias: str) -> str:
    return r"(?<!\w)" + re.escape(alias).replace(r"\ ", r"[^\S\n]+") + r"(?!\w)"


def uncertain(text: str, start: int, prefix_chars: int | None = None) -> bool:
    prefix_chars = default_limits()["uncertainty_prefix_chars"] if prefix_chars is None else prefix_chars
    prefix = text[max(0, start - prefix_chars):start]
    return bool(re.search(r"(?:\d\s*[-–—]|\b(?:от|до|около|примерно|менее|более)|"
                          r"\b(?:не|нет|без)(?:\s+\w+){0,2})\s*$", prefix, re.I))


def context(text: str, start: int, end: int, radius: int | None = None) -> str:
    radius = default_limits()["context_radius_chars"] if radius is None else radius
    return text[max(0, start - radius):min(len(text), end + radius)]


class Rules:
    def __init__(self, config: dict):
        self.config = config
        self.scores = config["rule_scores"]
        self.limits = config["rule_limits"]
        self.bounds = config["numeric_bounds"]
        self.model_rules = ModelRules(config)
        self.aliases = {}
        for kind in ["brands", "colors"]:
            self.aliases[kind] = [(canonical, re.compile(bounded_alias(alias), re.I))
                                  for canonical, aliases in config[kind].items() for alias in aliases]
        self.patterns = {
            "memory": re.compile(rf"(?<![\w.,])(?P<n>{NUMBER})\s*(?P<u>GB|ГБ)(?!\w)", re.I),
            "screen_inches": re.compile(rf"(?<![\w.,])(?P<n>{NUMBER})\s*(?P<u>дюйм\w*|inches?\b|[\"″])", re.I),
            "battery_mah": re.compile(rf"(?<![\w.,])(?P<n>(?:{NUMBER}|\d{{5}}))\s*(?P<u>м[аa]\s*(?:[*·⋅]\s*)?ч|mAh)(?!\w)", re.I),
            "capacity_l": re.compile(rf"(?<![\w.,])(?P<n>{NUMBER})\s*(?P<u>мл|ml|литр\w*|л|L)(?!\w)", re.I),
            "power_w": re.compile(rf"(?<![\w.,])(?P<n>{NUMBER})\s*(?P<u>кВт|kW|Вт|W)(?!\w)", re.I),
        }
        self.pair = re.compile(r"(?<![\w/])(?P<ram>\d{1,3})(?:\s*(?:GB|ГБ))?\s*[/+]\s*"
                               r"(?P<rom>\d{2,4})\s*(?:GB|ГБ)(?!\w)", re.I)
        self.roles = {
            "ram_gb": re.compile(r"оперативн\w*|\bОЗУ\b|\bRAM\b", re.I),
            "storage_gb": re.compile(r"встроенн\w*|постоянн\w*|\bROM\b|накопител\w*", re.I),
            "card": re.compile(r"карт\w*\s+памят\w*|micro\s*SD|SDXC|SDHC", re.I),
        }

    def make(self, attribute, value, field, offset, text, match, rule, score_key):
        return Candidate(attribute, value, UNITS.get(attribute), field,
                         offset + match.start(), offset + match.end(), match.group(), self.scores[score_key], rule)

    def uncertain(self, text, start):
        return uncertain(text, start, self.limits["uncertainty_prefix_chars"])

    def profile(self, product):
        return self.config["category_profiles"][product.category_id]

    def brand(self, product: Product):
        # Prefer a configured adjacent subbrand, never a brand mentioned later
        # in a comparison, compatibility phrase or another product name.
        matches = []
        text, positions = visible_view(product.title)
        for canonical, pattern in self.aliases["brands"]:
            if self.profile(product) == "smartphone" and canonical in {"GALAXY", "Galaxy Line"}:
                continue  # These kettle brands are not smartphone manufacturers.
            for m in pattern.finditer(text):
                if self.uncertain(text, m.start()) or re.search(r"\b(?:для|совместим\w*)\b", text[:m.start()], re.I):
                    continue
                if m.start() < self.limits["brand_prefix_chars"]:
                    matches.append((m.start(), -len(m.group()), canonical, m))
        if matches:
            _, _, canonical, m = min(matches, key=lambda x: x[:2])
            rule = "brand.explicit-title.v1"
            children = self.config.get("brand_subbrands", {}).get(canonical, [])
            adjacent = [item for item in matches if item[2] in children and item[0] >= m.end()
                        and re.fullmatch(r"[^\S\n]+", text[m.end():item[0]])]
            if adjacent:
                _, _, canonical, m = min(adjacent, key=lambda x: x[:2])
                rule = "brand.explicit-subbrand.v2"
            first, last = positions[m.start()], positions[m.end() - 1]
            if first is not None and last is not None and all(positions[m.start():m.end()]):
                yield Candidate("brand", canonical, None, "title", first[0], last[1],
                                product.title[first[0]:last[1]], self.scores["brand"], rule)

    def color_evidence_span(self, text: str, start: int, end: int) -> tuple[int, int]:
        """Keep approved marketing/texture words and adjacent generic labels.

        These words are evidence only, never extra colors or inferred shades.
        v0.1 can represent only one contiguous span in one input field.
        """
        modifiers = self.config.get("color_modifiers", {})
        generic = r"многоцветн\w*|multicolou?red"
        before = "|".join(re.escape(s) for s in modifiers.get("prefix", []))
        after = "|".join(re.escape(s) for s in modifiers.get("suffix", []))
        prefix = re.search(r"(?<!\w)(?:" + generic + ("|" + before if before else "")
                           + r")(?:(?:[^\S\n])|[,(/-])+$", text[:start], re.I)
        if prefix:
            start = prefix.start()
        suffix = re.match(r"(?:(?:[^\S\n])|[,)/-])+(?:" + generic + ("|" + after if after else "")
                          + r")(?!\w)", text[end:], re.I)
        if suffix:
            end += suffix.end()
        return start, end

    def colors(self, field: str, offset: int, text: str):
        found = [(canonical, m) for canonical, pattern in self.aliases["colors"]
                 for m in pattern.finditer(text)]
        for canonical, m in found:
            if any(other.start() <= m.start() and other.end() >= m.end()
                   and other.end() - other.start() > m.end() - m.start() for _, other in found):
                continue  # Do not turn dark blue into two colors.
            prefix = text[max(0, m.start() - self.limits["color_prefix_chars"]):m.start()]
            if re.search(r"(?:\w+-|\b(?:темно|тёмно|светло|ярко|бледно|глубок\w*|насыщенн\w*|dark|light|deep)\s+)$", prefix, re.I):
                continue  # An unconfigured shade/compound is not the basic color.
            local = context(text, m.start(), m.end(), self.limits["color_context_radius_chars"])
            if self.uncertain(text, m.start()) or re.search(r"подсветк|индикатор|упаковк|кнопк|шнур|ручк", local, re.I):
                continue
            if field == "description" and not re.search(r"цвет\w*|корпус\w*", local, re.I):
                continue
            if canonical == "титановый":
                # A material word is not a color. Description needs a color
                # label in the same clause; a bare title variant is allowed.
                clause_start = max(text.rfind(char, 0, m.start()) for char in ".;\n") + 1
                before = text[clause_start:m.start()][-self.limits["material_prefix_chars"]:]
                if re.search(r"\b(?:материал\w*|material|из)\b", before, re.I):
                    continue
                if field == "description" and not re.search(r"\bцвет\w*", before, re.I):
                    continue
                if re.search(r"\b(?:корпус\w*|body|case)\b", before, re.I) and not re.search(r"\bцвет\w*", before, re.I):
                    continue
                if re.match(r"\s+(?:корпус\w*|сплав\w*|материал\w*)\b", text[m.end():], re.I):
                    continue
                following = re.match(r"[^\S\n]+([A-Za-zА-Яа-яЁё]+)", text[m.end():])
                if (following and not re.fullmatch(r"многоцветн\w*|multicolou?red|Matte", following[1], re.I)
                        and not any(other.start() == m.end() + following.start(1) for _, other in found)):
                    continue  # Do not silently drop an unknown shade qualifier.
            start, end = self.color_evidence_span(text, m.start(), m.end())
            yield Candidate("color", canonical, None, field, offset + start, offset + end,
                            text[start:end], self.scores["color"], "color.explicit.v2")

    def memory_role(self, text: str, start: int, end: int) -> str | None:
        found = []
        for role, pattern in self.roles.items():
            for m in pattern.finditer(text):
                distance = start - m.end() if m.end() <= start else m.start() - end
                if 0 <= distance <= self.limits["memory_role_distance_chars"]:
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
            if self.uncertain(text, m.start()):
                continue
            ram, rom = int(m["ram"]), int(m["rom"])
            ram_min, ram_max = self.limits["memory_pair_ram_bounds"]
            rom_min, rom_max = self.limits["memory_pair_storage_bounds"]
            if not ram_min <= ram <= ram_max or not rom_min <= rom <= rom_max or ram >= rom:
                continue
            for attr, value in [("ram_gb", ram), ("storage_gb", rom)]:
                try:
                    normalized = numeric(attr, str(value), "GB", self.bounds)
                except ValueError:
                    continue
                yield self.make(attr, normalized, field, offset, text, m, "memory.title-pair.v1", "memory_pair")
        for m in self.patterns["memory"].finditer(text):
            if any(p.start() <= m.start() < p.end() for p in pairs) or self.uncertain(text, m.start()):
                continue
            role = self.memory_role(text, m.start(), m.end())
            if role not in {"ram_gb", "storage_gb"}:
                continue
            try:
                value = numeric(role, m["n"], m["u"], self.bounds)
            except ValueError:
                continue
            yield self.make(role, value, field, offset, text, m, "memory.context.v1", "memory_context")

    def quantities(self, product: Product, field: str, offset: int, text: str):
        attributes = (["screen_inches", "battery_mah"] if self.profile(product) == "smartphone"
                      else ["capacity_l", "power_w"])
        for attr in attributes:
            for m in self.patterns[attr].finditer(text):
                local = context(text, m.start(), m.end(), self.limits["context_radius_chars"])
                if self.uncertain(text, m.start()):
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
                    value = numeric(attr, m["n"], m["u"], self.bounds)
                except ValueError:
                    continue
                yield self.make(attr, value, field, offset, text, m, attr + ".explicit.v1", "quantity")

    def models(self, product: Product, field: str, text: str):
        for start, end, rule in self.model_rules.spans(product.category_id, field, text):
            fragment = text[start:end]
            yield Candidate("model", model_name(fragment), None, field, start, end,
                            fragment, self.scores["model"], rule)

    def candidates(self, product: Product):
        if "brand" in self.config["categories"][product.category_id]:
            yield from self.brand(product)
        for field in ["title", "description"]:
            source = getattr(product, field) or ""
            text, positions = visible_view(source)
            found = list(self.colors(field, 0, text))
            found.extend(self.models(product, field, text))
            if self.profile(product) == "smartphone":
                found.extend(self.memory(field, 0, text))
            found.extend(self.quantities(product, field, 0, text))
            for candidate in found:
                if candidate.attribute not in self.config["categories"][product.category_id]:
                    continue
                first, last = positions[candidate.start], positions[candidate.end - 1]
                if first is None or last is None:
                    continue
                yield replace(candidate, start=first[0], end=last[1], text=source[first[0]:last[1]])

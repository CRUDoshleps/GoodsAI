"""Bounded, text-only relation checks shared by candidate-producing methods.

This is a conservative syntax guard, not entity linking or category inference.
Structural candidate validation must run first. No target or catalogue lookup.
"""
import re

from goodsai.contracts import Product
from goodsai.text import visible_view


VERSION = "relation-1.0"
ACCESSORY = r"(?:чехо?л\w*|кабел\w*|зарядн\w*\s+устройств\w*|защитн\w*\s+стекл\w*|пленк\w*|плёнк\w*|крышк\w*|подставк\w*|запчаст\w*|адаптер\w*|case|cover|cable|charger)"
PRIMARY = r"(?:смартфон\w*|телефон\w*|электрочайник\w*|чайник\w*|smartphone|phone|kettle)"
TITLE_ACCESSORY = re.compile(r"^\s*(?:(?:универсальн\w*|оригинальн\w*|черн\w*|чёрн\w*|бел\w*|красн\w*|син\w*|прозрачн\w*|black|white|red|blue|transparent)\s+){0,2}" + ACCESSORY + r"\b", re.I)
BOUNDARY = re.compile(r"(?<!\d)\.(?!\d)|[!?;\n]|\b(?:но|однако|зато|but|however)\b", re.I)
FOREIGN = re.compile(
    r"\b(?:совместим\w*\s+(?:с|со)|подходит\s+(?:для|к)|предназначен\w*\s+для|"
    r"для\s+(?:модел\w*|смартфон\w*|телефон\w*|чайник\w*)|"
    r"compatible\s+with|designed\s+for|в\s+отличие\s+от|по\s+сравнению\s+с|"
    r"compared\s+(?:to|with)|аналог\w*\s+(?:модел\w*|с)|вместо)\b", re.I)
BUNDLE = re.compile(r"\b(?:в\s+комплект\w*\b|комплект\w*\s*[:=]|комплектаци\w*\s*[:=]|included\b|bundle\s*:)", re.I)
ACCESSORY_MENTION = re.compile(r"\b" + ACCESSORY + r"\b", re.I)
OTHER_OBJECT = re.compile(r"\b(?:друг\w*\s+" + PRIMARY + r"|упаковк\w*|коробк\w*|заварочн\w*\s+чайник\w*|"
                          r"внешн\w*\s+аккумулятор\w*|power\s*bank)\b", re.I)
MAIN_RESET = re.compile(r"\b(?:этот|данный|основной|сам)\s+" + PRIMARY + r"\b", re.I)
NEGATIVE = re.compile(r"\b(?:не|нет|без|no|not|without)\b", re.I)
EXCEPTION = re.compile(r"^\s*(?:только|менее|более|only|less|more)\b", re.I)
ATTRIBUTE_TERMS = {
    "brand": r"бренд\w*|производител\w*|brand|manufacturer",
    "model": r"модел\w*|model",
    "color": r"цвет\w*|корпус\w*|colou?r|body",
    "ram_gb": r"памят\w*|озу|ram|memory",
    "storage_gb": r"памят\w*|накопител\w*|rom|storage|memory",
    "screen_inches": r"экран\w*|диагонал\w*|диспле\w*|screen|display",
    "battery_mah": r"аккумулятор\w*|батаре\w*|емкост\w*|ёмкост\w*|battery|capacity",
    "capacity_l": r"объем\w*|объём\w*|емкост\w*|ёмкост\w*|capacity|volume",
    "power_w": r"мощност\w*|power",
}


class RelationVerifier:
    """Prepare visible/raw maps once per product, then assess each candidate.

    Context is limited to the current clause and 240 visible characters on
    either side. Rejected candidates never compete with supported main-product
    facts. A rejection does not assert the opposite fact.
    """
    def __init__(self, product: Product):
        self.views = {}
        for field in ("title", "description"):
            text, positions = visible_view(getattr(product, field) or "")
            starts, ends = {}, {}
            for index, pos in enumerate(positions):
                if pos is not None:
                    starts.setdefault(pos[0], index)
                    ends[pos[1]] = index + 1
            self.views[field] = (text, positions, starts, ends)
        title = self.views["title"][0]
        self.accessory_title = bool(TITLE_ACCESSORY.search(title))

    def reason(self, candidate) -> str | None:
        """Return a stable rejection reason, or None when no rule rejects it.

        Any structurally validated candidate with attribute/field/raw offsets
        can use this interface; score, rule ID and producing method are ignored.
        None means only 'not rejected', never proof of semantic correctness.
        """
        text, positions, starts, ends = self.views[candidate.field]
        start, end = starts.get(candidate.start), ends.get(candidate.end)
        if (start is None or end is None or start >= end
                or any(pos is None for pos in positions[start:end])):
            return "relation_nonvisible_evidence"
        if self.accessory_title:
            return "relation_accessory_product"

        # Sentence/HTML-block/contrast boundaries prevent leakage from a nearby
        # accessory sentence. Decimal points and model dots are not split.
        left, right = max(0, start - 240), min(len(text), end + 240)
        for boundary in BOUNDARY.finditer(text, left, right):
            if boundary.end() <= start:
                left = boundary.end()
            elif boundary.start() >= end:
                right = boundary.start()
                break
        prefix = text[left:start]
        suffix = text[end:right]
        resets = list(MAIN_RESET.finditer(prefix))
        if resets:
            prefix = prefix[resets[-1].start():]

        if FOREIGN.search(prefix):
            return "relation_foreign_entity"
        if BUNDLE.search(prefix):
            return "relation_bundle_item"
        accessory_mentions = [m for m in ACCESSORY_MENTION.finditer(prefix)
                              if not (re.search(r"\b(?:без|нет|without|no)\s*$", prefix[:m.start()], re.I)
                                      and "," in prefix[m.end():])]
        if OTHER_OBJECT.search(prefix) or accessory_mentions:
            return "relation_other_object"
        # Postposed ownership: 'цвет черный у чехла', '6 inches on another phone'.
        if re.match(r"\s*(?:у|для|of|on)\s+(?:" + ACCESSORY + r"|друг\w*\s+" + PRIMARY + r")\b", suffix, re.I):
            return "relation_other_object"

        # Negation must immediately govern the value or this attribute label;
        # 'без кабеля, мощность 2300 Вт' must not negate the appliance power.
        for marker in NEGATIVE.finditer(prefix):
            tail = prefix[marker.end():]
            if EXCEPTION.match(tail):
                continue
            words = re.findall(r"\w+", tail)
            terms = ATTRIBUTE_TERMS.get(candidate.attribute, r"(?!)")
            if (not words or (len(words) <= 5 and not re.search(r"[,()]", tail)
                              and re.search(r"\b(?:" + terms + r")\b", tail, re.I))):
                return "relation_negated"
        if re.match(r"\s*(?:не\s+(?:указан\w*|предусмотрен\w*|поддержива\w*)|отсутств\w*|not\s+(?:supported|included))\b", suffix, re.I):
            return "relation_negated"
        return None

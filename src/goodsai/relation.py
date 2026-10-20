"""Bounded, text-only relation checks shared by candidate-producing methods.

This is a conservative syntax guard, not entity linking or category inference.
Structural candidate validation must run first. No target or catalogue lookup.
"""
import re

from goodsai.contracts import Product
from goodsai.config import load_config
from goodsai.model_rules import DESCRIPTOR, ModelRules
from goodsai.text import visible_view


VERSION = "relation-1.2"
ACCESSORY = r"(?:чехо?л\w*|кабел\w*|зарядн\w*\s+устройств\w*|защитн\w*\s+стекл\w*|пленк\w*|плёнк\w*|крышк\w*|подставк\w*|запчаст\w*|адаптер\w*|case|cover|cable|charger)"
PRIMARY = r"(?:смартфон\w*|телефон\w*|электрочайник\w*|чайник\w*|smartphone|phone|kettle)"
# An explicit proper-name head, not a lookup for a particular manufacturer.
UPPER_NAME_HEAD = re.compile(r"^\s*(?i:" + PRIMARY + r")\s+(?P<name>[A-Z][A-Z&-]*(?:\s+[A-Z][A-Z&-]*){1,3})(?=\s+[A-Z][A-Za-z0-9.-]*\d)")
NAME_LABEL = re.compile(r"\b(?:бренд|производитель|модель|brand|manufacturer|model)\s*[:=]\s*(?P<name>[^\n;,.]+?)(?=\s+\b(?:цвет\w*|colou?r)\s*[:=]|[\n;,.]|$)", re.I)
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

# Explicit metatext only. A normal 'инструкция в комплекте' or JSON-formatted
# seller specification is not by itself a command/example of an output.
DIRECTIVE = re.compile(
    r"\b(?:игнорируй\w*\s+(?:правил\w*|предыдущ\w*|инструкц\w*)|"
    r"(?:верни|выведи|сгенерируй|напиши)\s+(?:\w+\s+){0,3}"
    r"(?:бренд|модел\w*|батаре\w*|мощност\w*|цвет|json|ответ|атрибут\w*)|"
    r"ignore\s+(?:previous|all|the)\s+(?:instructions|rules)|"
    r"(?:return|output|generate)\s+(?:the\s+)?(?:brand|model|battery|power|colou?r|json|answer))\b", re.I)
META_LABEL = re.compile(
    r"\b(?:служебн\w*\s+(?:вставк\w*|инструкц\w*|команд\w*)|"
    r"(?:system|assistant|developer)\s*:|"
    r"(?:пример|образец)\s+(?:json|ответа|вывода)|"
    r"(?:example|sample)\s+(?:json|output|response))", re.I)


def metatext_spans(text):
    """Mark explicit instruction clauses / labeled balanced JSON examples once.

    Sentence/HTML-block/line boundaries end a command. A labeled JSON example
    can cross these boundaries, but only up to its balanced closing delimiter.
    This is bounded syntactic attachment, not general prompt-injection detection.
    """
    spans = []
    markers = sorted(list(DIRECTIVE.finditer(text)) + list(META_LABEL.finditer(text)), key=lambda m: m.start())
    for marker in markers:
        if spans and marker.start() < spans[-1][1]:
            continue
        end = len(text)
        for boundary in BOUNDARY.finditer(text, marker.end()):
            end = boundary.start()
            break
        # A labeled JSON example remains an example across embedded newlines.
        if META_LABEL.fullmatch(marker.group()):
            tail = re.match(r"\s*[:=]?\s*(?:```(?:json)?\s*)?([\[{])", text[marker.end():], re.I)
            if tail:
                begin = marker.end() + tail.start(1)
                end = len(text)  # An unterminated explicit example is not product facts.
                stack, quoted, escaped = [], False, False
                for index in range(begin, len(text)):
                    char = text[index]
                    if quoted:
                        if escaped:
                            escaped = False
                        elif char == "\\":
                            escaped = True
                        elif char == '"':
                            quoted = False
                    elif char == '"':
                        quoted = True
                    elif char in "[{":
                        stack.append(char)
                    elif char in "]}":
                        if not stack or (stack.pop(), char) not in {("[", "]"), ("{", "}")}:
                            break
                        if not stack:
                            end = index + 1
                            break
        spans.append((marker.start(), end))
    return spans


class RelationVerifier:
    """Prepare visible/raw maps once per product, then assess each candidate.

    Context is limited to the current clause and 240 visible characters on
    either side. Rejected candidates never compete with supported main-product
    facts. A rejection does not assert the opposite fact.
    """
    def __init__(self, product: Product, config: dict | None = None, *, models=None):
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
        config = load_config() if config is None else config
        models = ModelRules(config) if models is None else models
        self.name_spans = {}
        self.metatext = {}
        for field, (text, _, _, _) in self.views.items():
            self.metatext[field] = metatext_spans(text)
            spans = [m.span('name') for m in NAME_LABEL.finditer(text)]
            if product.category_id in config['category_profiles']:
                spans.extend((a, b) for a, b, _ in models.spans(product.category_id, field, text))
            if field == 'title':
                descriptor = DESCRIPTOR.match(text)
                begin = descriptor.end() if descriptor else len(text) - len(text.lstrip())
                brand_end = models.brand_end(text[begin:], models.model_brands, repeated=True)
                if brand_end:
                    spans.append((begin, begin + brand_end))
                head = UPPER_NAME_HEAD.match(text)
                if head:
                    spans.append(head.span('name'))
            self.name_spans[field] = spans

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
        if any(start < b and end > a for a, b in self.metatext[candidate.field]):
            return "relation_instruction_or_example"
        if candidate.attribute == 'color' and any(start < b and end > a for a, b in self.name_spans[candidate.field]):
            return 'relation_name_token'

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

        if candidate.attribute == 'color':
            if re.search(r'(?:\w+-|\b(?:темно|тёмно|светло|ярко|бледно|глубок\w*|насыщенн\w*|dark|light|deep)\s+)$', prefix, re.I):
                return 'relation_unknown_color_modifier'
            material = list(re.finditer(r'\b(?:материал\w*|material)\b', prefix, re.I))
            if material and not re.search(r'\b(?:цвет\w*|colou?r)\b', prefix[material[-1].end():], re.I):
                return 'relation_material_not_color'

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

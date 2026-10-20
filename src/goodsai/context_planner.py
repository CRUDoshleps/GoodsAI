"""Conservative source-block selection. Unproven completeness means full context or abstain."""
from dataclasses import asdict, dataclass
import re

VERSION = 'source-context-1'
# Context deletion is allowed only for numeric fields with a closed unit scanner.
# Brand/model/unknown attribute grammars cannot prove mention completeness.
UNITS = {
    'ram_gb': r'GB|ГБ|ОЗУ|RAM', 'storage_gb': r'GB|ГБ|ПЗУ|ROM|памят',
    'screen_inches': r'дюйм|inch|экран|["″]', 'battery_mah': r'м[аa]|mAh|батар|аккум',
    'capacity_l': r'мл|ml|литр|объ[её]м|\bл\b|\bL\b', 'power_w': r'Вт|W|мощн',
}
DANGER = re.compile(r'\b(?:не|нет|без|ни|отсутст\w*|вместо|кроме|для|совместим\w*|microSD|SD|'
                    r'карт\w*|друг\w*|аксессуар\w*|чехол\w*|он|она|они|это|этот|эта|такой|указан\w*|'
                    r'выше|ниже|данн\w*|его|е[её]|поддерж\w*)\b', re.I)
SAFE_BOILERPLATE = re.compile(r'^(?:история бренда|упаковка|информация о доставке|условия доставки|подробности доставки|спасибо за интерес к товару)[.!?]?$' , re.I)
BOUNDARY = re.compile(r'(?:[.!?](?=\s|$)|\n+|</(?:p|div|li|tr|h[1-6])\s*>)', re.I)


@dataclass(frozen=True)
class SourceBlock:
    field: str
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class ContextPlan:
    version: str
    status: str
    reasons: tuple[str, ...]
    blocks: tuple[SourceBlock, ...]
    original_chars: int
    selected_chars: int

    def payload(self):
        return [asdict(block) for block in self.blocks]


def source_blocks(product):
    result = []
    for field in ('title', 'description'):
        source = getattr(product, field) or ''
        if not source:
            continue
        if field == 'title':
            result.append(SourceBlock(field, 0, len(source), source))
            continue
        start = 0
        for match in BOUNDARY.finditer(source):
            end = match.end()
            result.append(SourceBlock(field, start, end, source[start:end]))
            start = end
        if start < len(source):
            result.append(SourceBlock(field, start, len(source), source[start:]))
    return tuple(result)


def plan_context(product, attributes, max_chars=16000):
    if type(max_chars) is not int or not 128 <= max_chars <= 262144:
        raise ValueError('Invalid context budget')
    blocks = source_blocks(product)
    total = sum(len(b.text) for b in blocks)
    full_reason = None
    if not attributes or any(attr not in UNITS for attr in attributes):
        full_reason = 'scanner_incomplete'
    elif DANGER.search(product.title + '\n' + (product.description or '')):
        full_reason = 'negation_relation_or_reference'
    else:
        relevant = re.compile('|'.join(UNITS[attr] for attr in attributes), re.I)
        selected = set()
        for i, block in enumerate(blocks):
            # Unknown prose is never assumed irrelevant. Only explicit neutral headings
            # can be removed; scanner vocabulary alone is not a completeness proof.
            visible = re.sub(r'<[^>]*>', '', block.text).strip()
            if (block.field == 'title' or relevant.search(block.text) or re.search(r'\d', block.text)
                    or not SAFE_BOILERPLATE.fullmatch(visible)):
                selected.add(i)
                # Retain governing preceding/following sentences; no isolated quote windows.
                selected.update(j for j in (i-1, i+1) if 0 <= j < len(blocks))
        # Any two matching blocks can contradict even when the values differ only in prose.
        mentions = [b for b in blocks if relevant.search(b.text)]
        if len(mentions) > 1:
            full_reason = 'multiple_mentions'
        chosen = tuple(b for i,b in enumerate(blocks) if i in selected)
        if not mentions:
            full_reason = 'scanner_no_support'
    if full_reason:
        chosen = blocks
    count = sum(len(b.text) for b in chosen)
    if count > max_chars:
        return ContextPlan(VERSION, 'unavailable', (full_reason or 'selected_blocks', 'context_budget_exceeded'),
                           (), total, 0)
    status = 'full' if count == total else 'reduced'
    return ContextPlan(VERSION, status, (full_reason or 'mentions_neighbors_and_unproven_blocks',), chosen, total, count)

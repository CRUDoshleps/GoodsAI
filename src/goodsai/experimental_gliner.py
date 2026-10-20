"""Opt-in development hybrid: rules plus grounded, single-token brand suggestions.

Never imported by the default CLI/API. Scores are uncalibrated and all additions
require review. The artifact must be prepared explicitly before inference.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import time

from goodsai.contracts import Product, load_config, validate_prediction
from goodsai.rules import Candidate
from goodsai.span_index import visible_view
from goodsai.text import visible_span
from goodsai.verify import Extractor, validate_candidate
from goodsai.candidate_verifier import CandidateVerifier

CHECKPOINT = '443d26d654e0324125a96bebd8e796c14ff2efe6'
ENCODER = 'a0484667b22365f84929a935b5e50a51f71f159d'
WEIGHTS_SHA256 = '2100142f31627531497850659dcb3821c99d5e71c08a8e01a98e4b11ef32a199'
POLICY = 'gliner-brand-single-token-dev-v1'
LABELS = ['brand', 'product model']
THRESHOLD = 0.5
ROLE = re.compile(r'\b(?:для|совместим\w*|чехол\w*|аксессуар\w*|не|без)\b', re.I)
GENERIC = {'смартфон', 'чайник', 'электрочайник', 'телефон', 'smartphone', 'kettle'}


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def validate_artifact(root):
    """No pickle, remote model identifiers, dynamic Python or implicit downloads."""
    root = Path(root).resolve(strict=True)
    manifest = json.loads((root / 'artifact.json').read_text())
    expected = {'gliner/gliner_config.json', 'gliner/model.safetensors',
                'encoder/config.json', 'encoder/tokenizer_config.json', 'encoder/spm.model'}
    allowed = expected | {'artifact.json', 'gliner/original_gliner_config.json',
                          'gliner/README.md', 'encoder/README.md'}
    for path in root.rglob('*'):
        relative = path.relative_to(root)
        if '.cache' in relative.parts:
            continue  # Hugging Face download metadata is not an inference asset.
        if path.is_symlink() or path.is_file() and relative.as_posix() not in allowed:
            raise ValueError('Unlisted local model artifact file')
    if (manifest.get('checkpoint_revision') != CHECKPOINT or manifest.get('encoder_revision') != ENCODER
            or set(manifest.get('sha256', {})) != expected):
        raise ValueError('Unsupported local model artifact')
    if manifest['sha256']['gliner/model.safetensors'] != WEIGHTS_SHA256:
        raise ValueError('Unexpected checkpoint weights')
    for name, digest in manifest['sha256'].items():
        path = (root / name).resolve(strict=True)
        if not path.is_relative_to(root) or file_hash(path) != digest:
            raise ValueError('Local model artifact checksum mismatch')
    config = json.loads((root / 'gliner/gliner_config.json').read_text())
    if Path(config['model_name']).resolve() != root / 'encoder':
        raise ValueError('Encoder must resolve inside prepared artifact')
    for name in ('encoder/config.json', 'encoder/tokenizer_config.json'):
        if 'auto_map' in json.loads((root / name).read_text()):
            raise ValueError('Remote code mappings are forbidden')
    return root


class LocalGliner:
    """CPU-only loader, initialized once on the first eligible request."""
    def __init__(self, artifact):
        self.artifact = Path(artifact)
        self.model = None

    def predict(self, text):
        import torch
        if self.model is None:
            root = validate_artifact(self.artifact)
            from gliner import GLiNER
            torch.set_num_threads(2)
            self.model = GLiNER.from_pretrained(str(root / 'gliner'), local_files_only=True,
                                               map_location='cpu', strict=True)
            self.model.eval()
        with torch.inference_mode():
            return self.model.predict_entities(text, LABELS, threshold=THRESHOLD, flat_ner=False)


def brand_candidates(product, config, entities):
    """Map visible offsets back to untouched HTML, then apply development guards."""
    text, positions = visible_view(product.title)
    text, positions = text[:512], positions[:512]
    candidates = []
    for entity in entities:
        if not isinstance(entity, dict) or entity.get('label') != 'brand':
            continue
        start, end, score = entity.get('start'), entity.get('end'), entity.get('score')
        if (type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text)
                or type(score) not in (int, float) or not math.isfinite(score)
                or not THRESHOLD <= score <= 1):
            continue
        value = text[start:end]
        if (entity.get('text') != value or start >= 65 or len(value) > 60
                or len(value.split()) != 1 or value.casefold() in GENERIC
                or not re.search(r'[^\W\d_]', value) or ROLE.search(text[:start])):
            continue
        mapping = positions[start:end]
        if any(pos is None for pos in mapping):
            continue
        raw_start, raw_end = mapping[0][0], mapping[-1][1]
        # A single token may contain inline tags, but never hidden or block boundaries.
        if visible_span(product.title, raw_start, raw_end) != value:
            continue
        for canonical, aliases in config['brands'].items():
            if any(value.casefold() == alias.casefold() for alias in aliases):
                value = canonical
                break
        candidate = Candidate('brand', value, None, 'title', raw_start, raw_end,
                              product.title[raw_start:raw_end], float(score), POLICY)
        validate_candidate(candidate, product, config['categories'][product.category_id], config)
        candidates.append(candidate)
    return candidates


class HybridExtractor:
    """Explicitly constructed alternative to Extractor; never overwrites rule output."""
    def __init__(self, config, backend):
        self.config = config
        self.rules = Extractor(config)
        self.backend = backend
        self.failed = False
        self.last_diagnostics = {}

    def predict(self, product, run_id='experimental-gliner'):
        row = self.rules.predict(product, run_id)
        self.last_diagnostics = {'policy': POLICY, 'model_called': False}
        brand = next((a for a in row['attributes'] if a['attribute'] == 'brand'), None)
        if brand is None or brand['reason_codes'] != ['not_found_by_rules']:
            return row
        if len(product.title) > 65536:
            brand['reason_codes'].append('model_source_too_long')
            return row
        if self.failed:
            brand['reason_codes'].append('model_unavailable')
            return row
        text = visible_view(product.title)[0][:512]
        started = time.perf_counter()
        try:
            self.last_diagnostics['model_called'] = True
            candidates = brand_candidates(product, self.config, self.backend.predict(text))
        except (ImportError, OSError, ValueError, RuntimeError, KeyError, TypeError):
            # No exception text: backends may include input text or private paths.
            self.failed = True
            brand['reason_codes'].append('model_unavailable')
            self.last_diagnostics['failure'] = 'model_unavailable'
            return row
        finally:
            self.last_diagnostics['model_seconds'] = time.perf_counter() - started
        gate = CandidateVerifier(product, self.config, rules=self.rules.rules)
        rejected = set()
        verified = []
        for candidate in candidates:
            reason = gate.reason(candidate)
            if reason:
                rejected.add(reason)
            else:
                verified.append(candidate)
        candidates = verified
        self.last_diagnostics['rejected'] = sorted(rejected)
        if len({c.value for c in candidates}) > 1:
            brand['reason_codes'].append('conflicting_model_evidence')
        elif candidates:
            c = min(candidates, key=lambda c: (-c.score, c.start, c.end))
            brand.update(value=c.value, confidence=c.score, decision='review', method='model',
                         rule_id=c.rule_id, reason_codes=[],
                         evidence={'field':c.field, 'start':c.start, 'end':c.end, 'text':c.text})
        else:
            brand['reason_codes'].extend(sorted(rejected) or ['model_no_safe_candidate'])
        validate_prediction(row, self.config, product)
        return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--artifact', required=True)
    args = parser.parse_args()
    # Exclusive output creation; partial output remains visibly .partial on failure.
    target = Path(args.output)
    partial = target.with_suffix(target.suffix + '.partial')
    if target.exists():
        parser.error('Output already exists')
    extractor = HybridExtractor(load_config(), LocalGliner(args.artifact))
    with Path(args.input).open(encoding='utf-8') as source, partial.open('x', encoding='utf-8', newline='\n') as output:
        for line in source:
            if line.strip():
                product = Product.from_dict(json.loads(line))
                output.write(json.dumps(extractor.predict(product), ensure_ascii=False)+'\n')
    # Link is exclusive, so concurrent writers cannot replace a completed output.
    target.hardlink_to(partial)
    partial.unlink()


if __name__ == '__main__':
    main()

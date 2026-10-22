"""Candidate-specific experimental heuristics, never acceptance probabilities.

Scoring follows value selection and verification. No labels or identifiers enter
the feature vector. Learned scores estimate catalog agreement, not human probability.
"""
import math
import re

from goodsai.text import visible_view

VERSION = "context-v1"
LABELS = {
    "brand": r"бренд|производитель|brand",
    "model": r"модель|model",
    "storage_gb": r"накопитель|встроенная память|память устройства|storage|rom",
    "ram_gb": r"оперативная память|озу|ram",
    "screen_inches": r"диагональ(?: экрана)?|screen",
    "battery_mah": r"ёмкость аккумулятора|емкость аккумулятора|аккумулятор|батарея|battery",
    "color": r"цвет|color|colour",
    "capacity_l": r"объ[её]м|вместимость|capacity",
    "power_w": r"мощность|power",
}
UNIT = re.compile(r"(?:(?<![a-zа-яё])(?:gb|tb|гб|тб|mah|мач|вт|w|л|l|inch)\b|мА[·⋅]?ч|дюйм|[\"″])", re.I)


def validate_policy(value, config=None):
    if not isinstance(value, dict):
        raise ValueError("Confidence policy must be an object")
    if value.get('version') == 'learned-v1':
        from goodsai.learned_confidence import validate_model
        if set(value)!={'version','model'} or config is None:
            raise ValueError('learned-v1 requires a validated model and extraction config')
        validate_model(value['model'],config)
    elif set(value)!={"version"} or value.get("version") not in {"fixed-v1", VERSION}:
        raise ValueError("Unknown confidence policy; expected fixed-v1, context-v1 or learned-v1")
    return dict(value)


def normalized(text):
    return " ".join(text.casefold().split())


def feature_vector(product, attribute, candidates, views=None):
    """Only verified candidates of the selected value may corroborate it."""
    views = views or {f: visible_view(getattr(product, f) or "") for f in ("title", "description")}
    e = attribute["evidence"]
    text, positions = views[e["field"]]
    indices = [i for i, p in enumerate(positions) if p is not None and p[0] >= e["start"] and p[1] <= e["end"]]
    if not indices:
        raise ValueError("Confidence requires verified visible evidence")
    begin = indices[0]
    # Stay in the visible clause; a label in another table row/hidden node cannot boost a value.
    prefix = re.split(r"[\n;.!?]", text[max(0, begin - 60):begin])[-1]
    label = LABELS.get(attribute["attribute"])
    explicit = bool(label and re.search(r"\b(?:" + label + r")\s*[:=\-]?\s*$", prefix, re.I))
    evidence = "".join(text[i] for i in indices)
    unit = bool(attribute["unit"] and UNIT.search(evidence))
    fields = {c.field for c in candidates if (c.value, c.unit) == (attribute["value"], attribute["unit"])}
    corroborated = (fields == {"title", "description"}
                    and normalized(views["title"][0]) != normalized(views["description"][0]))
    return {
        "intercept": 1.0, "score": attribute["confidence"],
        "attribute=" + attribute["attribute"]: 1.0,
        "category=" + product.category_id: 1.0,
        "rule=" + attribute["rule_id"]: 1.0,
        "field=" + e["field"]: 1.0,
        "span_length": min(len(evidence), 100) / 100,
        "explicit_role": float(explicit), "explicit_unit": float(unit),
        "cross_field_agreement": float(corroborated),
    }


def contextual_score(vector):
    p = min(max(vector["score"], 1e-6), 1 - 1e-6)
    z = math.log(p / (1 - p))
    z += .35 * vector["explicit_role"] + .20 * vector["explicit_unit"] + .40 * vector["cross_field_agreement"]
    if not vector["explicit_role"] and not vector["explicit_unit"]:
        z -= .35
    return round(1 / (1 + math.exp(-z)), 6)


def row_features(product, row, grouped):
    views = {f: visible_view(getattr(product, f) or "") for f in ("title", "description")}
    return {a["attribute"]: feature_vector(product, a, grouped.get(a["attribute"], []), views)
            for a in row["attributes"] if a["value"] is not None and a["method"] == "rule"}


def apply_scores(product, row, grouped, config):
    policy=config['runtime'].get('confidence',{})
    if policy.get('version') not in {VERSION,'learned-v1'}:
        return
    vectors = row_features(product, row, grouped)
    for a in row["attributes"]:
        if a["attribute"] in vectors:
            if policy['version']=='learned-v1':
                from goodsai.learned_confidence import predict_score, scope_key
                a['confidence']=predict_score(vectors[a['attribute']],scope_key(product.category_id,a['attribute'],a['rule_id']),policy['model'])
            else:
                a["confidence"] = contextual_score(vectors[a["attribute"]])


def main():
    import argparse
    from pathlib import Path
    from goodsai.config import load_config, validate_config
    from goodsai.data import write_json
    parser = argparse.ArgumentParser(description="Create opt-in experimental context confidence profile")
    parser.add_argument("--base-config", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument('--model',type=Path)
    parser.add_argument('--model-sha256')
    args = parser.parse_args()
    config = load_config(args.base_config)
    config["runtime"]["confidence"] = {"version": VERSION}
    if args.model:
        import hashlib
        from goodsai.config import _read_json
        raw=args.model.read_bytes()
        if len(raw)>1048576 or not args.model_sha256 or hashlib.sha256(raw).hexdigest()!=args.model_sha256:
            parser.error('Explicit model SHA-256 must match artifact')
        config['runtime']['confidence']={'version':'learned-v1','model':_read_json(raw.decode('utf-8'))}
    elif args.model_sha256:
        parser.error('--model-sha256 requires --model')
    validate_config(config)
    if args.output.exists():
        parser.error("Refusing to overwrite an existing profile")
    write_json(args.output, config)


if __name__ == "__main__":
    main()

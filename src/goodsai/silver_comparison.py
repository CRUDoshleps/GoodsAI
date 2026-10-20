"""Paired catalog-silver transitions, without cancelling regressions against gains."""
from collections import Counter, defaultdict


def paired_changes(old, new):
    """Count transitions, never net away a regression against a gain elsewhere."""
    key = lambda p: (p["sku_id"], p["attribute"])
    old, new = list(old), list(new)
    a, b = {key(p): p for p in old}, {key(p): p for p in new}
    if len(a) != len(old) or len(b) != len(new):
        raise ValueError("duplicate_paired_identity")
    if a.keys() != b.keys():
        raise ValueError("paired_population_mismatch")
    total, slices, private = Counter(), defaultdict(Counter), []
    for identity in sorted(a):
        left, right = a[identity], b[identity]
        x, y = left["counts"], right["counts"]
        changes = {"new_tp": int(y["tp"] > x["tp"]), "lost_tp": int(y["tp"] < x["tp"]),
                   "new_fp": int(y["fp"] > x["fp"]), "removed_fp": int(y["fp"] < x["fp"]),
                   "new_fn": int(y["fn"] > x["fn"]), "removed_fn": int(y["fn"] < x["fn"])}
        total.update(changes)
        slices["attribute:" + right["attribute"]].update(changes)
        slices["category:" + right["category_id"]].update(changes)
        if any(changes.values()):
            private.append({"sku_id": identity[0], "attribute": identity[1], **changes,
                            "before_method": left["method"], "after_method": right["method"],
                            "support": right["support"], "reference_status": right["reference_status"]})
    return {"counts": dict(total), "slices": {k: dict(v) for k, v in sorted(slices.items())}}, private


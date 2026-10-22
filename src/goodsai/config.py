"""Versioned, strict configuration shared by batch, HTTP and rule inference."""
from copy import deepcopy
from functools import lru_cache
from importlib.resources import files
import json
import math
from pathlib import Path

ATTRIBUTES = {"brand", "model", "color", "storage_gb", "ram_gb", "screen_inches",
              "battery_mah", "capacity_l", "power_w"}
NUMERIC_ATTRIBUTES = ATTRIBUTES - {"brand", "model", "color"}
LEGACY_KEYS = {"schema_version", "rules_version", "dictionary_version", "seed", "categories",
               "brands", "colors", "brand_subbrands", "model_brand_aliases", "color_modifiers",
               "experiment_ablation"}
POLICY_KEYS = {"config_version", "category_profiles", "numeric_bounds", "rule_scores", "rule_limits", "runtime"}


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate configuration key")
        result[key] = value
    return result


def _read_json(text):
    def invalid_constant(value):
        raise ValueError("Configuration must contain finite JSON numbers")
    try:
        return json.loads(text, object_pairs_hook=_object, parse_constant=invalid_constant)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("Configuration must be a valid JSON object") from exc


@lru_cache(maxsize=1)
def _packaged():
    return _read_json(files("goodsai").joinpath("baseline.json").read_text(encoding="utf-8"))


def default_bounds():
    return deepcopy(_packaged()["numeric_bounds"])


def default_limits():
    return deepcopy(_packaged()["rule_limits"])


def default_api_limits():
    return deepcopy(_packaged()["runtime"]["api"])


LLM_EXTENSIONS = {"model_revision": None, "cache_namespace": "local", "cache_ttl_seconds": 3600, "context_planner": False, "context_max_chars": 16000, "span_selector": False, "selector_max_spans": 512}


def default_llm_policy():
    return {**deepcopy(_packaged()["runtime"]["llm"]), **LLM_EXTENSIONS}


def validate_llm_policy(policy):
    """One schema for profile, resolved overrides and low-level LLMSettings."""
    _keys(policy, set(default_llm_policy()) - set(LLM_EXTENSIONS), optional=LLM_EXTENSIONS, location="runtime.llm")
    policy = {**LLM_EXTENSIONS, **policy}
    if type(policy["span_selector"]) is not bool:
        raise ValueError("Span selector must be boolean")
    if type(policy["selector_max_spans"]) is not int or not 1 <= policy["selector_max_spans"] <= 2048:
        raise ValueError("Invalid selector span budget")
    if type(policy["context_planner"]) is not bool:
        raise ValueError("Context planner must be boolean")
    if type(policy["context_max_chars"]) is not int or not 128 <= policy["context_max_chars"] <= 262144:
        raise ValueError("Invalid context budget")
    _string(policy["cache_namespace"], "cache_namespace")
    if policy["model_revision"] is not None:
        _string(policy["model_revision"], "model_revision")
    if type(policy["cache_ttl_seconds"]) is not int or not 1 <= policy["cache_ttl_seconds"] <= 86400:
        raise ValueError("Cache TTL must be between 1 and 86400 seconds")
    if policy["model"] is not None:
        _string(policy["model"], "runtime.llm.model")
        if len(policy["model"]) > 200:
            raise ValueError("LLM model must have at most 200 characters")
    for key in ("max_calls", "daily_max_calls"):
        if type(policy[key]) is not int or policy[key] < 0:
            raise ValueError("LLM call budgets must be non-negative integers")
    for key, low, high in (("max_attempts", 1, 5), ("concurrency", 1, 8),
                           ("max_tokens", 64, 8192), ("circuit_breaker", 1, 100)):
        if type(policy[key]) is not int or not low <= policy[key] <= high:
            raise ValueError(f"LLM parameter outside supported integral range: {key}")
    _number(policy["timeout_seconds"], "runtime.llm.timeout_seconds")
    if not 1 <= policy["timeout_seconds"] <= 300:
        raise ValueError("LLM timeout must be between 1 and 300 seconds")
    if type(policy["json_mode"]) is not bool:
        raise ValueError("LLM json_mode must be a boolean")
    for key in ("price_input_per_1k", "price_output_per_1k"):
        if policy[key] is not None:
            _number(policy[key], key)
            if policy[key] < 0:
                raise ValueError("LLM prices must be non-negative")
    for key in ("cache_dir", "budget_ledger"):
        if policy[key] is not None:
            _string(policy[key], key)
    _number(policy["request_deadline_seconds"], "runtime.llm.request_deadline_seconds")
    if not 1 <= policy["request_deadline_seconds"] <= 900:
        raise ValueError("LLM request deadline must be between 1 and 900 seconds")
    for key, low, high in (("max_response_bytes", 4096, 16 * 1024 * 1024), ("max_proposals", 1, 256)):
        if type(policy[key]) is not int or not low <= policy[key] <= high:
            raise ValueError(f"LLM parameter outside supported integral range: {key}")
    return deepcopy(policy)


def _keys(value, required, optional=(), location="config"):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise ValueError(f"Invalid keys in configuration section: {location}")


def _string(value, location):
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"Expected a nonempty trimmed string: {location}")


def _strings(value, location, nonempty=False):
    if not isinstance(value, list) or (nonempty and not value):
        raise ValueError(f"Expected a string list: {location}")
    for item in value:
        _string(item, location)
    if len(set(value)) != len(value):
        raise ValueError(f"Duplicate items in configuration section: {location}")


def _number(value, location):
    if type(value) not in (int, float) or (type(value) is float and not math.isfinite(value)):
        raise ValueError(f"Expected a finite number: {location}")


def _bounds(value, location, integers=False):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"Expected [minimum, maximum]: {location}")
    for item in value:
        _number(item, location)
        if integers and type(item) is not int:
            raise ValueError(f"Expected integral bounds: {location}")
    if not 0 < value[0] <= value[1]:
        raise ValueError(f"Expected positive ordered bounds: {location}")


def validate_config(config: dict) -> dict:
    """Return an independent effective config; explicitly migrate legacy v0.1 files.

    A versioned file must be complete. Only files without any new policy keys
    use the documented legacy migration; partial v1 configs never get defaults.
    """
    if not isinstance(config, dict):
        raise ValueError("Configuration must be a JSON object")
    config = deepcopy(config)
    required_legacy = {"schema_version", "rules_version", "dictionary_version", "seed", "categories", "brands", "colors"}
    if "config_version" not in config:
        _keys(config, required_legacy, LEGACY_KEYS - required_legacy, "legacy config")
        defaults = _packaged()
        for key in POLICY_KEYS:
            config[key] = deepcopy(defaults[key])
        config["category_profiles"] = {key: defaults["category_profiles"].get(key) for key in config["categories"]} if isinstance(config["categories"], dict) else {}
    _keys(config, required_legacy | POLICY_KEYS | ({"category_registry"} if config.get("config_version") == "2" else set()), LEGACY_KEYS - required_legacy)
    if config["schema_version"] != "0.1" or not isinstance(config["config_version"], str) or config["config_version"] not in {"1", "2"}:
        raise ValueError("Unsupported schema_version or config_version")
    for key in ("rules_version", "dictionary_version", "seed"):
        _string(config[key], key)
    if "experiment_ablation" in config and config["experiment_ablation"] not in {"disable_model_generation_only", "relation:before", "relation:after"}:
        raise ValueError("Unsupported experiment ablation")

    learned = {}
    if config["config_version"] == "2":
        from goodsai.category_registry import validate_registry
        learned = validate_registry(config["category_registry"])["categories"]

    categories = config["categories"]
    if not isinstance(categories, dict) or not categories:
        raise ValueError("categories must be a nonempty object")
    profiles = config["category_profiles"]
    _keys(profiles, categories, location="category_profiles")
    profile_attributes = {
        "smartphone": ATTRIBUTES - {"capacity_l", "power_w"},
        "kettle": {"brand", "model", "color", "capacity_l", "power_w"},
    }
    if set(learned) - set(categories):
        raise ValueError("Registry contains an unconfigured category")
    for category, attributes in categories.items():
        _string(category, "category ID")
        _strings(attributes, "category attributes", nonempty=True)
        profile = profiles[category]
        if profile == "learned" and category in learned:
            if set(attributes) != set(learned[category]["attributes"]):
                raise ValueError("Registry and configured attributes differ")
            continue
        if category in learned:
            raise ValueError("Registry category must use learned profile")
        if not isinstance(profile, str) or profile not in profile_attributes or set(attributes) - profile_attributes[profile]:
            raise ValueError("Unsupported category profile or attributes")

    for kind in ("brands", "colors"):
        aliases = config[kind]
        if not isinstance(aliases, dict) or not aliases:
            raise ValueError(f"{kind} must be a nonempty alias dictionary")
        owners = {}
        for canonical, spellings in aliases.items():
            _string(canonical, kind)
            _strings(spellings, kind, nonempty=True)
            for alias in spellings:
                if alias.casefold() in owners and owners[alias.casefold()] != canonical:
                    raise ValueError(f"Ambiguous alias in {kind}")
                owners[alias.casefold()] = canonical
    subbrands = config.get("brand_subbrands", {})
    if not isinstance(subbrands, dict):
        raise ValueError("brand_subbrands must be an object")
    for parent, children in subbrands.items():
        _strings(children, "brand_subbrands")
        if parent not in config["brands"] or any(child not in config["brands"] or child == parent for child in children):
            raise ValueError("Unknown or self-referencing subbrand")
    _strings(config.get("model_brand_aliases", []), "model_brand_aliases")
    modifiers = config.get("color_modifiers", {})
    _keys(modifiers, (), {"prefix", "suffix"}, "color_modifiers")
    for values in modifiers.values():
        _strings(values, "color_modifiers")

    _keys(config["numeric_bounds"], NUMERIC_ATTRIBUTES, location="numeric_bounds")
    for attribute, bounds in config["numeric_bounds"].items():
        _bounds(bounds, attribute, integers=attribute in {"ram_gb", "storage_gb", "battery_mah"})
    score_names = {"brand", "color", "model", "memory_pair", "memory_context", "quantity"}
    _keys(config["rule_scores"], score_names, location="rule_scores")
    for key, score in config["rule_scores"].items():
        _number(score, key)
        if not 0 <= score <= 1:
            raise ValueError("Rule scores must be between 0 and 1")
    limits = config["rule_limits"]
    limit_names = {"brand_prefix_chars", "uncertainty_prefix_chars", "context_radius_chars",
                   "color_context_radius_chars", "color_prefix_chars", "material_prefix_chars",
                   "memory_role_distance_chars", "memory_pair_ram_bounds", "memory_pair_storage_bounds"}
    _keys(limits, limit_names, location="rule_limits")
    for key, limit in limits.items():
        if key.endswith("_bounds"):
            _bounds(limit, key, integers=True)
        elif type(limit) is not int or limit <= 0:
            raise ValueError("Rule windows must be positive integers")

    runtime = config["runtime"]
    _keys(runtime, {"llm_enabled", "auto_accept_enabled", "api"},
          {"llm", "review_threshold", "auto_accept", "auto_accept_policies", "confidence"}, location="runtime")
    if "confidence" in runtime:
        from goodsai.confidence import validate_policy
        runtime["confidence"] = validate_policy(runtime["confidence"], config)
    if runtime["llm_enabled"] is not False or type(runtime["auto_accept_enabled"]) is not bool:
        raise ValueError("LLM profile flag must be false; auto_accept_enabled must be boolean")
    from goodsai.storage_acceptance import validate_policy, validate_cell_policies, bound_cells
    if "auto_accept" in runtime:
        runtime["auto_accept"] = validate_policy(runtime["auto_accept"])
    # Per category x attribute decision policy. Absent section (old profiles) means
    # the default: audited cells bound, everything else review.
    if "auto_accept_policies" in runtime:
        runtime["auto_accept_policies"] = validate_cell_policies(runtime["auto_accept_policies"])
    if runtime["auto_accept_enabled"]:
        if "auto_accept" not in runtime:
            raise ValueError("auto_accept requires the explicit approved storage pilot policy")
        if not bound_cells(config):
            raise ValueError("auto_accept_enabled requires at least one audited category/attribute cell")
        # The audited scope may not silently inherit modified rules/dictionaries,
        # bounds, categories, source grammars or experimental ablations.
        baseline = _packaged()
        if ({k: v for k, v in config.items() if k != "runtime"}
                != {k: v for k, v in baseline.items() if k != "runtime"}):
            raise ValueError("Storage pilot requires the audited default extraction profile")
    # Backward-compatible completion of old v1/v2 profiles. A present section is complete.
    runtime.setdefault("llm", default_llm_policy())
    runtime.setdefault("review_threshold", None)
    if runtime["review_threshold"] is not None:
        raise ValueError("Review threshold requires calibration; only null is supported")
    runtime["llm"] = validate_llm_policy(runtime["llm"])
    _keys(runtime["api"], {"max_body_bytes", "limit_concurrency", "timeout_keep_alive_seconds"}, location="runtime.api")
    if any(type(value) is not int or value <= 0 for value in runtime["api"].values()):
        raise ValueError("API limits must be positive integers")
    return config


def load_config(path: str | Path | None = None) -> dict:
    raw = _read_json(Path(path).read_text(encoding="utf-8")) if path is not None else _packaged()
    return validate_config(raw)

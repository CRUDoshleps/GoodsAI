"""Resolve non-secret runtime policy consistently for CLI and HTTP entry points."""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path

from goodsai.config import validate_config, validate_llm_policy
from goodsai.storage_acceptance import effective_cell_policies

# Endpoint/key stay solely in the provider environment, never in policy snapshots.
ENV_FIELDS = {
    "GOODSAI_LLM_SPAN_SELECTOR": ("span_selector", bool),
    "GOODSAI_LLM_SELECTOR_MAX_SPANS": ("selector_max_spans", int),
    "GOODSAI_LLM_CONTEXT_PLANNER": ("context_planner", bool),
    "GOODSAI_LLM_CONTEXT_MAX_CHARS": ("context_max_chars", int),
    "GOODSAI_LLM_MODEL_REVISION": ("model_revision", str),
    "GOODSAI_LLM_CACHE_NAMESPACE": ("cache_namespace", str),
    "GOODSAI_LLM_CACHE_TTL": ("cache_ttl_seconds", int),
    "GOODSAI_LLM_MODEL": ("model", str),
    "GOODSAI_LLM_MAX_CALLS": ("max_calls", int),
    "GOODSAI_LLM_DAILY_MAX_CALLS": ("daily_max_calls", int),
    "GOODSAI_LLM_TIMEOUT": ("timeout_seconds", float),
    "GOODSAI_LLM_ATTEMPTS": ("max_attempts", int),
    "GOODSAI_LLM_MAX_TOKENS": ("max_tokens", int),
    "GOODSAI_LLM_CONCURRENCY": ("concurrency", int),
    "GOODSAI_LLM_CIRCUIT_BREAKER": ("circuit_breaker", int),
    "GOODSAI_LLM_JSON_MODE": ("json_mode", bool),
    "GOODSAI_LLM_PRICE_INPUT_PER_1K": ("price_input_per_1k", float),
    "GOODSAI_LLM_PRICE_OUTPUT_PER_1K": ("price_output_per_1k", float),
    "GOODSAI_LLM_CACHE_DIR": ("cache_dir", str),
    "GOODSAI_LLM_BUDGET_FILE": ("budget_ledger", str),
    "GOODSAI_LLM_REQUEST_DEADLINE": ("request_deadline_seconds", float),
    "GOODSAI_LLM_MAX_RESPONSE_BYTES": ("max_response_bytes", int),
    "GOODSAI_LLM_MAX_PROPOSALS": ("max_proposals", int),
}
SECRET_ENV = {"GOODSAI_LLM_BASE_URL", "GOODSAI_LLM_API_KEY"}


def _boolean(value):
    if isinstance(value, str) and value.lower() in {"1", "true", "0", "false"}:
        return value.lower() in {"1", "true"}
    raise ValueError("Invalid boolean runtime environment parameter")


def resolve_runtime_policy(config, *, enabled=None, overrides=None, environ=None):
    """Profile < recognized environment < explicit CLI options; no implicit LLM calls.

    CLI passes enabled explicitly (its --llm opt-in); HTTP uses GOODSAI_LLM_ENABLED.
    Validate even disabled settings so broken production configuration fails early.
    """
    config = validate_config(config)
    env = os.environ if environ is None else environ
    known = set(ENV_FIELDS) | SECRET_ENV | {"GOODSAI_LLM_ENABLED"}
    if any(key.startswith("GOODSAI_LLM_") and key not in known for key in env):
        raise ValueError("Unknown GOODSAI_LLM environment parameter")
    env_enabled = _boolean(env.get("GOODSAI_LLM_ENABLED", "0"))
    enabled = env_enabled if enabled is None else enabled
    if type(enabled) is not bool:
        raise ValueError("LLM enabled must be a boolean")
    settings = deepcopy(config["runtime"]["llm"])
    for name, (field, kind) in ENV_FIELDS.items():
        if name in env:
            try:
                settings[field] = _boolean(env[name]) if kind is bool else kind(env[name])
            except (TypeError, ValueError, OverflowError):
                # Never echo an untrusted environment value or a secret-bearing URL.
                raise ValueError(f"Invalid runtime environment parameter: {name}") from None
    for name, value in (overrides or {}).items():
        if name not in settings:
            raise ValueError("Unknown LLM runtime override")
        if value is not None:  # argparse defaults must not override profile/environment.
            settings[name] = str(value) if isinstance(value, Path) else value
    settings = validate_llm_policy(settings)
    if enabled and not settings["model"]:
        raise ValueError("LLM requires --llm-model, GOODSAI_LLM_MODEL or runtime.llm.model")
    if enabled and settings["budget_ledger"] is None:
        raise ValueError("Enabled LLM requires a shared budget ledger")
    policy = {"policy_version": "1", "llm_enabled": enabled, "llm": settings,
            "decisions": {"confidence_kind": "heuristic", "review_threshold": None,
                          "auto_accept_enabled": config["runtime"]["auto_accept_enabled"],
                          "auto_accept_policies": effective_cell_policies(config)}}
    from goodsai.storage_acceptance import metadata
    if "confidence" in config["runtime"]:
        policy["decisions"]["confidence"] = deepcopy(config["runtime"]["confidence"])
    acceptance = metadata(config)
    if acceptance is not None:
        policy["decisions"]["auto_accept"] = acceptance
    return policy


def llm_settings(policy):
    from goodsai.llm import LLMSettings
    values = deepcopy(policy["llm"])
    for name in ("cache_dir", "budget_ledger"):
        values[name] = Path(values[name]) if values[name] is not None else None
    return LLMSettings(**values)


def policy_for_settings(config, settings=None):
    """Snapshot actual library settings, without reading process environment."""
    policy = resolve_runtime_policy(config, enabled=False, environ={})
    if settings is not None:
        values = asdict(settings)
        for name in ("cache_dir", "budget_ledger"):
            values[name] = str(values[name]) if values[name] is not None else None
        policy.update(llm_enabled=True, llm=validate_llm_policy(values))
    return policy


def policy_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def runtime_metadata(config, policy):
    """Both hashes are effective, resolved and secret-free; profile hash stays separate."""
    effective = {"profile": validate_config(config), "runtime_policy": deepcopy(policy)}
    return {"runtime_policy": deepcopy(policy), "runtime_policy_sha256": policy_hash(policy),
            "effective_config": effective, "effective_config_sha256": policy_hash(effective)}

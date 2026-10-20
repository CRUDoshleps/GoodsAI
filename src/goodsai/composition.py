"""Single composition root for CLI and HTTP; injection is Python-only, never profile code."""
from copy import deepcopy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from goodsai.candidate_verifier import VerifierFactory
from goodsai.category_registry import Registry
from goodsai.config import validate_config, validate_llm_policy
from goodsai.policy import llm_settings, policy_for_settings, runtime_metadata
from goodsai.rules import Rules
from goodsai.stages import (CandidateSource, GateFactory, PredictionSink, Predictor,
                            Provider, Router, ValueNormalizer)
from goodsai.storage import FilePredictionSink
from goodsai.verify import Extractor

if TYPE_CHECKING:
    from goodsai.llm import LLMExtractor


@dataclass(frozen=True)
class Components:
    """Trusted, process-local overrides; no dynamic imports or config/SKU lookups."""
    source: CandidateSource | None = None
    normalizer: ValueNormalizer | None = None
    gate_factory: GateFactory | None = None
    router: Router | None = None
    provider: Provider | None = None
    sink: PredictionSink | None = None


@dataclass(frozen=True)
class PipelineRuntime:
    config: dict
    policy: dict
    predictor: Predictor
    sink: PredictionSink
    llm: "LLMExtractor | None" = None
    metadata: dict = field(default_factory=dict)


def build_runtime(config: dict, policy: dict | None = None, *,
                  components: Components | None = None, legacy_llm=None) -> PipelineRuntime:
    """Resolve dependencies once from explicit validated config/policy snapshots.

    Environment policy precedence belongs to entrypoints. Credentials are read
    only by the opt-in live provider factory. Disabled mode never creates it.
    ``legacy_llm`` keeps the existing batch Python API and its accumulated stats.
    """
    config = validate_config(config)
    policy = deepcopy(policy if policy is not None else policy_for_settings(
        config, legacy_llm.settings if legacy_llm is not None else None))
    # Entry points resolve precedence before assembly, but injected library policy
    # must still obey the exact v1 shape and current review-only decision policy.
    checked = policy_for_settings(config)
    checked["llm"] = validate_llm_policy(policy.get("llm"))
    checked["llm_enabled"] = policy.get("llm_enabled")
    if (type(checked["llm_enabled"]) is not bool or policy != checked
            or (checked["llm_enabled"] and not checked["llm"]["model"])):
        raise ValueError("Invalid runtime policy snapshot")
    if legacy_llm is None and policy["llm_enabled"] and policy["llm"]["budget_ledger"] is None:
        raise ValueError("Enabled LLM requires a shared budget ledger")
    metadata = runtime_metadata(config, policy)
    parts = components if components is not None else Components()
    if legacy_llm is not None:
        if components is not None or legacy_llm.config != config or not policy["llm_enabled"]:
            raise ValueError("Injected LLM must match the runtime profile and enabled policy")
        if llm_settings(policy) != legacy_llm.settings:
            raise ValueError("Injected LLM settings differ from runtime policy")
        return PipelineRuntime(config, policy, legacy_llm, FilePredictionSink(), legacy_llm, metadata)
    if not policy["llm_enabled"] and (parts.provider is not None or parts.router is not None):
        raise ValueError("Provider/router injection requires an enabled LLM policy")
    registry = Registry(config)
    # Source grammar and verification grammar are separate dependencies: a model
    # source need not expose Rules internals to cross the same gate.
    support = Rules(config)
    source = parts.source if parts.source is not None else support
    normalizer = parts.normalizer if parts.normalizer is not None else registry
    gates = parts.gate_factory if parts.gate_factory is not None else VerifierFactory(
        config, registry=registry, rules=support, normalizer=normalizer)
    predictor = Extractor(config, source=source, registry=registry, gate_factory=gates)
    llm = None
    if policy["llm_enabled"]:
        from goodsai.llm import LLMExtractor, has_signal, provider_from_env
        from goodsai.routing import SignalRouter
        settings = llm_settings(policy)
        provider = parts.provider if parts.provider is not None else provider_from_env(settings)
        router = parts.router if parts.router is not None else SignalRouter(config, has_signal)
        llm = LLMExtractor(config, provider, settings, rules=predictor, gate_factory=gates, router=router)
        predictor = llm
    sink = parts.sink if parts.sink is not None else FilePredictionSink()
    return PipelineRuntime(config, policy, predictor, sink, llm, metadata)

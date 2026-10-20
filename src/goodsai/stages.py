"""Internal v1 stage contracts. Transport and source implementations stay separate."""
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, ContextManager, Iterable, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from goodsai.contracts import Product

STAGE_CONTRACT_VERSION = "1"


@dataclass(frozen=True)
class Candidate:
    attribute: str
    value: str
    unit: str | None
    field: str
    start: int
    end: int
    text: str
    score: float
    rule_id: str


class CandidateSource(Protocol):
    def candidates(self, product: "Product") -> Iterable[Candidate]: ...


class CandidateGate(Protocol):
    def reason(self, candidate: Candidate) -> str | None: ...


class GateFactory(Protocol):
    def create(self, product: "Product") -> CandidateGate: ...


class Predictor(Protocol):
    def predict(self, product: "Product", run_id: str = "rules-v0") -> dict: ...


class ValueNormalizer(Protocol):
    def normalize(self, category_id: str, attribute: str, value: str, unit: str | None) -> str: ...


class Router(Protocol):
    """Select a subset of eligible gaps; cannot authorize data access or overwrite facts."""
    def select(self, product: "Product", eligible: tuple[str, ...]) -> tuple[str, ...]: ...


@dataclass(frozen=True)
class ProviderResponse:
    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str | None = None
    attempts: int = 1


class Provider(Protocol):
    model: str

    def complete(self, messages: list[dict], max_tokens: int, *, deadline: float | None = None,
                 reserve_attempt: Callable[[], str | None] | None = None) -> ProviderResponse: ...


class PredictionSink(Protocol):
    """Stage a data/manifest pair; publish together only after successful context exit."""
    def stage(self, output: Path) -> ContextManager[tuple[Path, Path]]: ...


class CategoryRegistry(Protocol):
    def attributes(self, category_id: str) -> tuple[str, ...]: ...

    def unit(self, category_id: str, attribute: str) -> str | None: ...

    def normalize(self, category_id: str, attribute: str, value: str, unit: str | None) -> str: ...

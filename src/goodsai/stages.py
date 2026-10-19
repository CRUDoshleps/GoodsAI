"""Internal v1 stage contracts. Transport and source implementations stay separate."""
from dataclasses import dataclass
from typing import Iterable, Protocol, TYPE_CHECKING

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


class CategoryRegistry(Protocol):
    def attributes(self, category_id: str) -> tuple[str, ...]: ...

    def unit(self, category_id: str, attribute: str) -> str | None: ...

    def normalize(self, category_id: str, attribute: str, value: str, unit: str | None) -> str: ...

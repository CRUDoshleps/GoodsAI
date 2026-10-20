"""Rules-first routing policy, independent of transports and provider IO."""
from typing import Callable

from goodsai.contracts import Product


class SignalRouter:
    def __init__(self, config: dict, signal: Callable[[Product, str, dict], bool]):
        self.config, self.signal = config, signal

    def select(self, product: Product, eligible: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(attr for attr in eligible if self.signal(product, attr, self.config))

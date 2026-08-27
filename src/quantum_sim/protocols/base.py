from abc import ABC, abstractmethod
from typing import Any


class BaseProtocol(ABC):
    @abstractmethod
    def setup(self, *args, **kwargs) -> Any:
        pass

    @abstractmethod
    def transmit(self, *args, **kwargs) -> Any:
        pass

    @abstractmethod
    def measure(self, *args, **kwargs) -> Any:
        pass

    @abstractmethod
    def process(self, *args, **kwargs) -> Any:
        pass

    @abstractmethod
    def run(self, *args, **kwargs) -> Any:
        pass

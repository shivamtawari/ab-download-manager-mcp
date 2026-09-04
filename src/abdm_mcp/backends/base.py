"""Abstract base class for ABDM backend implementations."""

from abc import ABC, abstractmethod


class AbstractBaseBackend(ABC):
    """Abstract interface for communicating with AB Download Manager."""

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if this backend is currently reachable and operational."""
        pass

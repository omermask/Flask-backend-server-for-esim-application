from app.providers.registry import ProviderRegistry

# Auto-discover all providers at import time
ProviderRegistry.discover_all()

__all__ = ["ProviderRegistry"]

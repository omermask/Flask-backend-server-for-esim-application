from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import Any

from app.providers.base import ESIMProviderBase, PaymentProviderBase, SMSProviderBase

logger = logging.getLogger("esim-ego")

_PROVIDER_CATEGORIES = ["sms", "esim", "payment"]


class ProviderRegistry:
    _sms: dict[str, type[SMSProviderBase]] = {}
    _esim: dict[str, type[ESIMProviderBase]] = {}
    _payment: dict[str, type[PaymentProviderBase]] = {}
    _loaded: bool = False

    @classmethod
    def discover_all(cls) -> None:
        if cls._loaded:
            return
        cls._loaded = True
        for category in _PROVIDER_CATEGORIES:
            module_path = f"app.providers.{category}"
            try:
                package = importlib.import_module(module_path)
                for _importer, modname, _ispkg in pkgutil.iter_modules(
                    package.__path__
                ):
                    importlib.import_module(f"{module_path}.{modname}")
                    logger.debug("Loaded provider: %s.%s", category, modname)
            except ModuleNotFoundError:
                logger.warning("Provider category not found: %s", module_path)
            except Exception as e:
                logger.error("Failed to load %s providers: %s", category, e)

    @classmethod
    def _ensure_loaded(cls) -> None:
        cls.discover_all()

    @classmethod
    def register_sms(cls, name: str, provider_cls: type[SMSProviderBase]) -> None:
        cls._sms[name.lower()] = provider_cls

    @classmethod
    def register_esim(cls, name: str, provider_cls: type[ESIMProviderBase]) -> None:
        cls._esim[name.lower()] = provider_cls

    @classmethod
    def register_payment(cls, name: str, provider_cls: type[PaymentProviderBase]) -> None:
        cls._payment[name.lower()] = provider_cls

    @classmethod
    def get_sms(cls, name: str) -> SMSProviderBase | None:
        cls._ensure_loaded()
        provider_cls = cls._sms.get(name.lower())
        return provider_cls() if provider_cls else None

    @classmethod
    def get_esim(cls, name: str) -> ESIMProviderBase | None:
        cls._ensure_loaded()
        provider_cls = cls._esim.get(name.lower())
        return provider_cls() if provider_cls else None

    @classmethod
    def get_payment(cls, name: str) -> PaymentProviderBase | None:
        cls._ensure_loaded()
        provider_cls = cls._payment.get(name.lower())
        return provider_cls() if provider_cls else None

    @classmethod
    def get_all_payments(cls) -> list[PaymentProviderBase]:
        cls._ensure_loaded()
        return [cls() for cls in cls._payment.values()]

    @classmethod
    def available_sms(cls) -> list[str]:
        cls._ensure_loaded()
        return list(cls._sms.keys())

    @classmethod
    def available_esim(cls) -> list[str]:
        cls._ensure_loaded()
        return list(cls._esim.keys())

    @classmethod
    def available_payments(cls) -> list[str]:
        cls._ensure_loaded()
        return list(cls._payment.keys())


def sms_provider(name: str):
    def wrapper(cls: type[SMSProviderBase]) -> type[SMSProviderBase]:
        ProviderRegistry.register_sms(name, cls)
        return cls
    return wrapper


def esim_provider(name: str):
    def wrapper(cls: type[ESIMProviderBase]) -> type[ESIMProviderBase]:
        ProviderRegistry.register_esim(name, cls)
        return cls
    return wrapper


def payment_provider(name: str):
    def wrapper(cls: type[PaymentProviderBase]) -> type[PaymentProviderBase]:
        ProviderRegistry.register_payment(name, cls)
        return cls
    return wrapper

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class SMSProviderBase(ABC):

    @abstractmethod
    def send_otp(self, phone: str, otp: str, lang: str = "en") -> dict[str, Any]:
        ...

    @abstractmethod
    def send_sms(self, phone: str, message: str, lang: str = "en") -> dict[str, Any]:
        ...

    def verify_otp(self, phone: str, code: str, request_id: str, expire: bool = True) -> dict[str, Any]:
        raise NotImplementedError

    def get_balance(self) -> dict[str, Any]:
        raise NotImplementedError


class ESIMProviderBase(ABC):

    @abstractmethod
    def activate_bundle(self, iccid: str, bundle_name: str) -> dict:
        ...

    @abstractmethod
    def get_bundle_status(self, iccid: str, bundle_name: str) -> dict:
        ...

    @abstractmethod
    def create_order(self, bundle_id: str, **kwargs) -> dict:
        ...

    @abstractmethod
    def apply_bundle(self, iccid: str, bundle_id: str, **kwargs) -> dict:
        ...

    @abstractmethod
    def get_install_details(self, reference: str) -> dict:
        ...

    def get_catalogue(self) -> dict:
        raise NotImplementedError

    def get_pricing(self, bundle_ids: list[str] | None = None) -> dict:
        raise NotImplementedError

    def handle_usage_callback(self, data: dict) -> dict:
        raise NotImplementedError


class PaymentProviderBase(ABC):

    @abstractmethod
    def initiate_payment(self, amount: int, order_id: str, callback_url: str) -> dict:
        ...

    @abstractmethod
    def verify_webhook(self, data: dict, signature: str) -> bool:
        ...

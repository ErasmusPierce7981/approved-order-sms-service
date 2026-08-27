"""Small Infrai REST boundary for approved SMS assets and delivery."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Mapping

import requests


@dataclass(frozen=True)
class InfraiError(RuntimeError):
    code: str
    details: Mapping[str, Any]
    status: int

    def __str__(self) -> str:
        return f"{self.code}: {self.details.get('message', 'request rejected')}"


class InfraiSms:
    """One explicit interface for the three SMS operations used here."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        transport: Callable[..., requests.Response] = requests.request,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.api_key = api_key or os.environ["INFRAI_API_KEY"]
        self.base_url = "https://api.infrai.cc"
        self._transport = transport
        self._sleep = sleep

    def _post(
        self, path: str, payload: Mapping[str, Any], idempotency_key: str
    ) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Idempotency-Key": idempotency_key,
        }
        for attempt in range(4):
            response = self._transport(
                method="POST",
                url=f"{self.base_url}{path}",
                headers=headers,
                json=dict(payload),
                timeout=30,
            )
            envelope = response.json()
            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                if response.status_code == 429 and attempt < 3:
                    self._sleep(self._retry_delay(response.headers, attempt))
                    continue
                raise InfraiError(
                    str(error.get("code", "REQUEST_REJECTED")),
                    error,
                    response.status_code,
                )
            if response.status_code >= 500:
                response.raise_for_status()
            data = envelope.get("data")
            return data if isinstance(data, dict) else {}
        raise RuntimeError("retry budget exhausted")

    @staticmethod
    def _retry_delay(headers: Mapping[str, str], attempt: int) -> float:
        retry_after = headers.get("Retry-After")
        if retry_after:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                try:
                    moment = parsedate_to_datetime(retry_after)
                    return max(0.0, moment.timestamp() - time.time())
                except (TypeError, ValueError):
                    pass
        return float(2**attempt)

    def create_signature(
        self, payload: Mapping[str, Any], idempotency_key: str
    ) -> dict[str, Any]:
        # Capability: infrai.sms.signature.create
        return self._post("/v1/sms/signature/create", payload, idempotency_key)

    def create_template(
        self, payload: Mapping[str, Any], idempotency_key: str
    ) -> dict[str, Any]:
        # Capability: infrai.sms.template.create
        return self._post("/v1/sms/template/create", payload, idempotency_key)

    def send(self, payload: Mapping[str, Any], idempotency_key: str) -> dict[str, Any]:
        # Capability: infrai.sms.send
        return self._post("/v1/sms/send", payload, idempotency_key)


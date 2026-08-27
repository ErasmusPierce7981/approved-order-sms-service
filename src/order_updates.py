"""Deterministic policy for selecting approved e-commerce SMS assets."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class OrderStage(str, Enum):
    CHECKOUT = "checkout"
    FULFILLMENT = "fulfillment"
    RECEIPT = "receipt"
    ORDER_UPDATE = "order_update"


@dataclass(frozen=True)
class ApprovedAsset:
    signature: str
    template: str


@dataclass(frozen=True)
class OrderUpdateRequest:
    order_id: str
    phone: str
    stage: OrderStage

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "OrderUpdateRequest":
        order_id = value.get("order_id")
        phone = value.get("phone")
        stage = value.get("stage")
        if not isinstance(order_id, str) or not order_id.strip():
            raise ValueError("order_id must be a non-empty string")
        if not isinstance(phone, str) or not phone.strip():
            raise ValueError("phone must be a non-empty string")
        if not isinstance(stage, str):
            raise ValueError("stage must be a string")
        return cls(order_id.strip(), phone.strip(), OrderStage(stage))


class ApprovedCatalog:
    def __init__(self, assets: Mapping[OrderStage, ApprovedAsset]) -> None:
        self._assets = dict(assets)

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "ApprovedCatalog":
        assets: dict[OrderStage, ApprovedAsset] = {}
        for stage_name, raw in value.items():
            stage = OrderStage(stage_name)
            if not isinstance(raw, dict):
                raise ValueError(f"catalog entry {stage_name!r} must be an object")
            signature = raw.get("signature")
            template = raw.get("template")
            if not isinstance(signature, str) or not signature:
                raise ValueError(f"catalog entry {stage_name!r} needs a signature")
            if not isinstance(template, str) or not template:
                raise ValueError(f"catalog entry {stage_name!r} needs a template")
            assets[stage] = ApprovedAsset(signature, template)
        return cls(assets)

    def select(self, request: OrderUpdateRequest) -> ApprovedAsset:
        try:
            return self._assets[request.stage]
        except KeyError as exc:
            raise ValueError(f"no approved assets for {request.stage.value}") from exc


def delivery_key(request: OrderUpdateRequest) -> str:
    """Keep repeated delivery attempts attached to one business event."""
    return f"order:{request.order_id}:{request.stage.value}"


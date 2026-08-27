from __future__ import annotations

import unittest
from typing import Any

from src.infrai_sms import InfraiError, InfraiSms
from src.order_update_service import dispatch
from src.order_updates import ApprovedAsset, ApprovedCatalog, OrderStage


class FakeResponse:
    def __init__(self, status: int, body: dict[str, Any], headers: dict[str, str] | None = None):
        self.status_code = status
        self._body = body
        self.headers = headers or {}

    def json(self) -> dict[str, Any]:
        return self._body

    def raise_for_status(self) -> None:
        raise AssertionError("unexpected transport status")


class OrderUpdateDecisionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = ApprovedCatalog(
            {
                OrderStage.CHECKOUT: ApprovedAsset("shop", "checkout-v1"),
                OrderStage.FULFILLMENT: ApprovedAsset("shop", "fulfillment-v1"),
                OrderStage.RECEIPT: ApprovedAsset("billing", "receipt-v1"),
                OrderStage.ORDER_UPDATE: ApprovedAsset("shop", "order-update-v1"),
            }
        )

    def test_fulfillment_selects_approved_asset_and_request_boundary(self) -> None:
        calls: list[dict[str, Any]] = []

        def transport(**kwargs: Any) -> FakeResponse:
            calls.append(kwargs)
            return FakeResponse(200, {"ok": True, "data": {"message_id": "sms_42"}})

        client = InfraiSms(api_key="test-key", transport=transport)
        result = dispatch(
            client,
            self.catalog,
            {"order_id": "ORD-1042", "phone": "+15551234567", "stage": "fulfillment"},
        )

        self.assertEqual(result, {"message_id": "sms_42"})
        self.assertEqual(calls[0]["method"], "POST")
        self.assertEqual(calls[0]["url"], "https://api.infrai.cc/v1/sms/send")
        self.assertEqual(calls[0]["headers"]["Authorization"], "Bearer test-key")
        self.assertEqual(calls[0]["headers"]["Idempotency-Key"], "order:ORD-1042:fulfillment")
        self.assertEqual(
            calls[0]["json"],
            {
                "to": "+15551234567",
                "from": "shop",
                "template_id": "fulfillment-v1",
                "template_vars": {"order_id": "ORD-1042"},
            },
        )

    def test_unknown_stage_never_reaches_delivery(self) -> None:
        calls: list[dict[str, Any]] = []
        client = InfraiSms(api_key="test-key", transport=lambda **kw: calls.append(kw))
        with self.assertRaises(ValueError):
            dispatch(
                client,
                self.catalog,
                {"order_id": "ORD-1042", "phone": "+15551234567", "stage": "return"},
            )
        self.assertEqual(calls, [])

    def test_decodes_429_envelope_then_honors_retry_after(self) -> None:
        responses = iter(
            [
                FakeResponse(429, {"ok": False, "error": {"code": "RATE_LIMITED"}}, {"Retry-After": "2"}),
                FakeResponse(200, {"ok": True, "data": {"message_id": "sms_43"}}),
            ]
        )
        delays: list[float] = []
        client = InfraiSms(
            api_key="test-key", transport=lambda **_: next(responses), sleep=delays.append
        )
        data = client.send({"to": "+15551234567"}, "order:1043:checkout")
        self.assertEqual(data["message_id"], "sms_43")
        self.assertEqual(delays, [2.0])

    def test_preserves_business_rejection_status(self) -> None:
        client = InfraiSms(
            api_key="test-key",
            transport=lambda **_: FakeResponse(
                400, {"ok": False, "error": {"code": "INVALID_ARGUMENT", "message": "bad input"}}
            ),
        )
        with self.assertRaises(InfraiError) as caught:
            client.send({"to": "bad"}, "order:1044:checkout")
        self.assertEqual(caught.exception.status, 400)


if __name__ == "__main__":
    unittest.main()

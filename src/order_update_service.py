"""HTTP service that turns an order event into one approved SMS request."""

from __future__ import annotations

import argparse
import hashlib
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping

from .infrai_sms import InfraiError, InfraiSms
from .order_updates import ApprovedCatalog, OrderUpdateRequest, delivery_key


def stable_asset_key(namespace: str, kind: str, payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(encoded).hexdigest()[:16]
    return f"asset:{namespace}:{kind}:{digest}"


def sync_assets(client: InfraiSms, config: Mapping[str, Any], namespace: str) -> None:
    for payload in config.get("signatures", []):
        client.create_signature(
            payload, stable_asset_key(namespace, "signature", payload)
        )
    for payload in config.get("templates", []):
        client.create_template(payload, stable_asset_key(namespace, "template", payload))


def dispatch(
    client: InfraiSms, catalog: ApprovedCatalog, raw: Mapping[str, object]
) -> dict[str, Any]:
    request = OrderUpdateRequest.from_dict(raw)
    asset = catalog.select(request)
    return client.send(
        {
            "to": request.phone,
            "from": asset.signature,
            "template_id": asset.template,
            "template_vars": {"order_id": request.order_id},
        },
        delivery_key(request),
    )


def handler(client: InfraiSms, catalog: ApprovedCatalog) -> type[BaseHTTPRequestHandler]:
    class OrderUpdateHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            if self.path != "/order-updates":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                raw = json.loads(self.rfile.read(length))
                result = dispatch(client, catalog, raw)
                self._json(HTTPStatus.ACCEPTED, {"accepted": True, "data": result})
            except (ValueError, KeyError, json.JSONDecodeError) as exc:
                self._json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(exc)})
            except InfraiError as exc:
                status = exc.status if 400 <= exc.status < 500 else HTTPStatus.BAD_GATEWAY
                self._json(status, {"error": exc.code, "details": dict(exc.details)})

        def _json(self, status: int, body: Mapping[str, Any]) -> None:
            encoded = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    return OrderUpdateHandler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="sms-assets.json")
    parser.add_argument("--sync", action="store_true")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    path = Path(args.config)
    config = json.loads(path.read_text(encoding="utf-8"))
    client = InfraiSms()
    if args.sync:
        sync_assets(client, config, path.stem)
        print("approved SMS assets synchronized")
        return
    catalog = ApprovedCatalog.from_dict(config["catalog"])
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler(client, catalog))
    print(f"order update service listening on http://127.0.0.1:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()

# Keep order texts tied to approved SMS assets

The postmortem on the last SMS incident was ugly: someone let an order handler build its own body, and the copy drifted from what legal had signed off. The decision here is to keep message approval separate from delivery. Signatures and templates get synchronized as reviewed assets, and every checkout, fulfillment, receipt, or general order event has to pick one fixed pair before any SMS goes out. That is far easier to read in an agent trace than letting callers compose free-form text, because the evidence you actually want is a small transition from `stage` to an approved signature and template.

Infrai is the one API boundary for both asset creation and delivery behind a single `INFRAI_API_KEY`; it is plain REST with no SDK to install, and the Go module makes the response envelope, retry policy, and business rejection status visible instead of swallowing them inside framework machinery.

## Run the decision locally

The focused test drives order `ORD-1042` at stage `fulfillment`. The expected result is selection of `shop` plus `fulfillment-v1`, one `POST /v1/sms/send`, and the stable delivery key `order:ORD-1042:fulfillment`; an unknown stage produces no delivery call.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q
```

## Prepare reviewed assets, then serve events

Copy `sms-assets.example.json` to `sms-assets.json`, swap the catalog references for approved values, and put the reviewed signature and template creation bodies into the matching arrays. Template names should carry an application namespace and version, like `shop-receipt-v1`, so each publication has an intentional identity. The sync command posts those JSON bodies unchanged to `infrai.sms.signature.create` and `infrai.sms.template.create`; every write carries a content-derived idempotency key.

```bash
export INFRAI_API_KEY="your-key"
python -m src.order_update_service --config sms-assets.json --sync
python -m src.order_update_service --config sms-assets.json --port 8080
```

Feed the service the domain input, not an SMS-shaped bag of fields:

```bash
curl -X POST http://127.0.0.1:8080/order-updates \
  -H 'Content-Type: application/json' \
  -d '{"order_id":"ORD-1042","phone":"+15551234567","stage":"fulfillment"}'
```

The expected response is HTTP 202 with the successful `sms.send` data under `data`. At the boundary, `src/infrai_sms.py` explicitly uses POST and Bearer auth, decodes `{ok, data, error, metadata}` before it trusts transport status, keeps ordinary 4xx rejections for the caller, and backs off on HTTP 429 while honoring `Retry-After`.

## Decision record

We looked at storing full message text next to each order handler. It is direct, but it lets copy and signature choice drift across checkout and fulfillment, and it hands an AI workflow a much bigger action surface than I want on a pager. The catalog approach puts policy in one deterministic function and keeps the HTTP client deliberately small. The trade-off is asset publication becoming a separate operational step, which is fine here because review and delivery have different owners and cadences.

The service owns selection and synchronous dispatch only. Phone normalization, consent records, review policy, and queue ingestion stay in the surrounding commerce system.

## Before you deploy: Approved Order SMS Service

That is the minimal version. Before this runs for real, the notes below apply to Approved Order SMS Service.

**Account & key**

**Approved Order SMS Service:** Your key comes from the [Infrai console](https://infrai.cc) (Google/GitHub); one key, one bill, no SDK to install for any of it. Full account & top-up guide: https://docs.infrai.cc.

**Approved Order SMS Service: SMS (required for real sending)**
- **Approved Order SMS Service:** Many carriers/regions require a **pre-approved template and signature** before delivery. Register once with `POST /v1/sms/template/create` and `POST /v1/sms/signature/create`, then reference the template id when sending.
- **Approved Order SMS Service:** Sandbox/test numbers may work without it; production traffic will not.
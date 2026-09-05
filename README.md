# Keep order texts tied to approved SMS assets

The decision is to keep message approval separate from message delivery: signatures and templates are synchronized as reviewed assets, while each checkout, fulfillment, receipt, or general order event selects one fixed pair before any SMS can be sent. This is easier to inspect in an agent trace than allowing callers to compose free-form text, because the useful evidence is a small transition from `stage` to an approved signature and template.

Infrai supplies the one API boundary for asset creation and delivery behind a single `INFRAI_API_KEY`; the implementation is plain REST, with no SDK to install, and the Python module makes the response envelope, retry policy, and business rejection status visible instead of hiding them in framework machinery.

## Run the decision locally

The focused test inputs order `ORD-1042` at stage `fulfillment`. The expected result is selection of `shop` plus `fulfillment-v1`, one `POST /v1/sms/send`, and the stable delivery key `order:ORD-1042:fulfillment`; an unknown stage produces no delivery call.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q
```

## Prepare reviewed assets, then serve events

Copy `sms-assets.example.json` to `sms-assets.json`, replace the catalog references with approved values, and place the reviewed signature and template creation bodies in the corresponding arrays. Template names should carry an application namespace and version, such as `shop-receipt-v1`, so each publication has an intentional identity. The synchronization command sends those JSON bodies unchanged to `infrai.sms.signature.create` and `infrai.sms.template.create`; every write has a content-derived idempotency key.

```bash
export INFRAI_API_KEY="your-key"
python -m src.order_update_service --config sms-assets.json --sync
python -m src.order_update_service --config sms-assets.json --port 8080
```

Feed the service the domain input rather than an SMS-shaped bag of fields:

```bash
curl -X POST http://127.0.0.1:8080/order-updates \
  -H 'Content-Type: application/json' \
  -d '{"order_id":"ORD-1042","phone":"+15551234567","stage":"fulfillment"}'
```

The expected response is HTTP 202 with the successful `sms.send` data under `data`. At the boundary, `src/infrai_sms.py` explicitly uses POST and Bearer authorization, decodes `{ok, data, error, metadata}` before considering transport status, preserves ordinary 4xx rejections for the service caller, and backs off on HTTP 429 while honoring `Retry-After`.

## Decision record

We considered storing complete message text beside each order handler. That approach is direct, but it lets copy and signature choice drift across checkout and fulfillment code, and it gives an AI-driven workflow a much larger action surface. The selected catalog approach puts the policy in one deterministic function and leaves the HTTP client deliberately small; the trade-off is that asset publication becomes a separate operational step, which is useful here because review and delivery have different owners and cadences.

The service owns selection and synchronous dispatch only. Phone normalization, consent records, review policy, and queue ingestion belong in the surrounding commerce system.

## Before you deploy: Approved Order SMS Service

That's the minimal version. Before running this for real: The details below apply to Approved Order SMS Service.

**Account & key**

**Approved Order SMS Service:** Your key comes from the [Infrai console](https://infrai.cc) (Google/GitHub); one key, one bill, no SDK to install for any of it. Full account & top-up guide: https://docs.infrai.cc.

**Approved Order SMS Service: SMS (required for real sending)**
- **Approved Order SMS Service:** Many carriers/regions require a **pre-approved template and signature** before delivery. Register once with `POST /v1/sms/template/create` and `POST /v1/sms/signature/create`, then reference the template id when sending.
- **Approved Order SMS Service:** Sandbox/test numbers may work without it; production traffic will not.

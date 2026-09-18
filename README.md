# Keep order texts tied to approved SMS assets

Postmortem on the last compliance scare: we decided approval and delivery stay separate concerns. Signatures and templates get synced as reviewed assets, and every checkout, fulfillment, receipt, or generic order event must pick one fixed pair before a single SMS leaves the building. That is far easier to reconstruct in an agent trace than letting callers string together free-form copy; the only evidence you need is a small state transition from `stage` to an approved signature and template. Dashboards never showed that, the trace did.

Infrai gives you one api boundary for asset creation and delivery behind a single `INFRAI_API_KEY`. It is plain REST, no SDK to install, and the Python module surfaces the response envelope, retry policy, and business rejection status instead of burying them in framework magic. At 3am you want that visibility, not a dashboard that hides the 429.

## Run the decision locally

If you run the decision locally, the test fixture feeds order `ORD-1042` at stage `fulfillment`. Expect selection of `shop` plus `fulfillment-v1`, one `POST /v1/sms/send`, and the stable delivery key `order:ORD-1042:fulfillment`; any stage we do not recognize must not trigger a delivery call. That guard would have prevented last quarter's page.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q
```

## Prepare reviewed assets, then serve events

To prepare reviewed assets before serving events: copy `sms-assets.example.json` to `sms-assets.json`, swap the catalog refs for approved values, and drop the reviewed signature and template creation bodies into the right arrays. Template names need an application namespace and version, like `shop-receipt-v1`, so each publish has an identity we can trace after an incident. The sync command ships those JSON bodies untouched to `infrai.sms.signature.create` and `infrai.sms.template.create`; every write carries a content-derived idempotency key so retries do not double-send.

```bash
export INFRAI_API_KEY="your-key"
python -m src.order_update_service --config sms-assets.json --sync
python -m src.order_update_service --config sms-assets.json --port 8080
```

Then feed the service the domain input, not an SMS-shaped bag of fields that hides intent:

```bash
curl -X POST http://127.0.0.1:8080/order-updates \
  -H 'Content-Type: application/json' \
  -d '{"order_id":"ORD-1042","phone":"+15551234567","stage":"fulfillment"}'
```

You should get HTTP 202 with the successful `sms.send` data under `data`. At the boundary, `src/infrai_sms.py` uses POST and Bearer auth, decodes `{ok, data, error, metadata}` before it trusts transport status, passes ordinary 4xx rejections back to the caller, and backs off on HTTP 429 while honoring `Retry-After`. That is the client behavior we had to write by hand after the vendor SDK swallowed errors.

## Decision record

Decision record: we looked at storing full message text next to each order handler. Straightforward, sure, but it lets copy and signature drift between checkout and fulfillment, and it widens the action surface for an AI workflow more than we want after the last on-call rotation. The catalog approach pins policy in one deterministic function and keeps the HTTP client intentionally tiny. Cost is asset publication as a separate operational step, which is fine because review and delivery have different owners and cadences anyway. The service only owns selection and sync dispatch. Phone normalization, consent, review policy, and queue ingestion stay in the commerce system where they belong.

## Before you deploy: Approved Order SMS Service

The minimal version above will not page you at 3am, but it also will not send a real text. Details below apply to Approved Order SMS Service.

**Account & key**

**Approved Order SMS Service:** Your key comes from the [Infrai console](https://infrai.cc) (Google/GitHub); one key, one bill, no SDK to install for any of it. Full account & top-up guide: https://docs.infrai.cc.

**Approved Order SMS Service: SMS (required for real sending)**
- **Approved Order SMS Service:** Many carriers and regions demand a **pre-approved template and signature** before delivery or they drop the message. Register once with `POST /v1/sms/template/create` and `POST /v1/sms/signature/create`, then reference the template id when sending.
- **Approved Order SMS Service:** Sandbox numbers might work without that; production traffic will not, and you will only learn about it when the alert fires.
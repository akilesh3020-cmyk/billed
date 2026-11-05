# Billed: invoicing that runs on your own Claude

Claude writes the invoice. Billed saves it, lets a person edit it, tracks payment and serves a live client link.
There is no AI SDK, model call or API key anywhere in this repo.

## Deploy (about 10 minutes)
1. Push this folder to a new GitHub repo.
2. Render.com > New > Blueprint > pick the repo (it reads render.yaml). Or create a Web Service manually:
   - Build: `pip install -r requirements.txt`
   - Start: `uvicorn app:app --host 0.0.0.0 --port $PORT`
   - Env vars: `SECRET_KEY` (random), `DEMO_PASS` (test password), `DEMO_TOKEN` (random string, fixes your MCP link)
   - Optional `BASE_URL=https://your-app.onrender.com` so links in Claude replies are exact.
3. Data is SQLite. For anything beyond a demo, attach a persistent disk (render.yaml does) and set `DATA_DIR=/data`.
   Free instances sleep after idle time. Open the URL once before recording or reviewers get a cold start.

## Submission details
- Live app: https://YOUR-APP.onrender.com   login: `demo` / the DEMO_PASS you set
- MCP link: https://YOUR-APP.onrender.com/mcp/YOUR_DEMO_TOKEN
- Connect in Claude: Settings > Connectors > Add custom connector > name "Billed" > paste the MCP link > Add.
  Then in a chat, enable the Billed connector and try:
  "Invoice Acme Ltd (billing@acme.com) for 3 days of design at 500 USD per day plus a 200 USD logo fee, 5% tax, due in 14 days, and mark it sent."

## Run locally
    pip install -r requirements.txt
    uvicorn app:app --reload      # login demo / demo1234

## How it is built
- `POST /mcp/{token}` is a stateless MCP (streamable HTTP, JSON replies) server with 7 tools:
  create_invoice, list_invoices, get_invoice, update_invoice, set_invoice_status, get_summary, set_business_profile.
- The token in the URL identifies the customer, so each customer has a private link and no OAuth is needed for v1.
- Web UI: signup/login, dashboard with totals, invoice editor with live totals, public client page `/i/{id}` (print to PDF).
- Overdue is computed from due date, not stored.

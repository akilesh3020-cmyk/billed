"""Billed: invoicing that runs on the customer's own Claude.

Claude (connected over MCP) does the drafting. This app only stores, edits,
serves and tracks invoices. There is no AI SDK, model call or AI key in here.
"""
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import datetime as dt
from contextlib import contextmanager

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from jinja2 import DictLoader, Environment, select_autoescape
from starlette.middleware.sessions import SessionMiddleware

from templates import TEMPLATES

DATA_DIR = os.environ.get("DATA_DIR", ".")
DB_PATH = os.path.join(DATA_DIR, "billed.db")
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
DEMO_USER = os.environ.get("DEMO_USER", "demo")
DEMO_PASS = os.environ.get("DEMO_PASS", "demo1234")
DEMO_TOKEN = os.environ.get("DEMO_TOKEN", "")

app = FastAPI(title="Billed")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=60 * 60 * 24 * 14, same_site="lax")

env = Environment(loader=DictLoader(TEMPLATES), autoescape=select_autoescape(["html"]))
env.filters["money"] = lambda v: "{:,.2f}".format(float(v or 0))


def render(name, request=None, **ctx):
    return HTMLResponse(env.get_template(name).render(request=request, **ctx))


# ---------------------------------------------------------------- database
@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    with db() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS users(
              id INTEGER PRIMARY KEY, username TEXT UNIQUE, pw TEXT, token TEXT UNIQUE,
              business_name TEXT DEFAULT '', payment_details TEXT DEFAULT '', created TEXT);
            CREATE TABLE IF NOT EXISTS invoices(
              id INTEGER PRIMARY KEY, user_id INTEGER, number TEXT, public_id TEXT UNIQUE,
              client_name TEXT, client_email TEXT DEFAULT '', currency TEXT DEFAULT 'USD',
              items TEXT DEFAULT '[]', tax_percent REAL DEFAULT 0, notes TEXT DEFAULT '',
              status TEXT DEFAULT 'draft', issue_date TEXT, due_date TEXT, paid_date TEXT,
              created TEXT, updated TEXT, UNIQUE(user_id, number));
            """
        )
        if not c.execute("SELECT 1 FROM users WHERE username=?", (DEMO_USER,)).fetchone():
            c.execute(
                "INSERT INTO users(username,pw,token,business_name,payment_details,created) VALUES(?,?,?,?,?,?)",
                (DEMO_USER, hash_pw(DEMO_PASS), DEMO_TOKEN or secrets.token_urlsafe(24),
                 "Demo Studio", "Bank transfer: Demo Bank, IBAN AE00 0000 0000 0000 0000 000", now()),
            )


def now():
    return dt.datetime.utcnow().isoformat(timespec="seconds")


def today():
    return dt.date.today()


def hash_pw(pw):
    salt = secrets.token_hex(8)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200_000).hex()
    return f"{salt}${h}"


def check_pw(pw, stored):
    try:
        salt, h = stored.split("$")
    except ValueError:
        return False
    return hmac.compare_digest(hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200_000).hex(), h)


@app.on_event("startup")
def _startup():
    init_db()


# ------------------------------------------------------------ invoice logic
STATUSES = ("draft", "sent", "paid", "void")


def clean_items(items):
    out = []
    for it in items or []:
        desc = str(it.get("description", "")).strip()
        if not desc:
            continue
        qty = float(it.get("quantity", 1) or 0)
        price = float(it.get("unit_price", 0) or 0)
        if qty < 0 or price < 0:
            raise ValueError("quantity and unit_price must be zero or more")
        out.append({"description": desc, "quantity": qty, "unit_price": price})
    return out


def totals(items, tax_percent):
    sub = round(sum(i["quantity"] * i["unit_price"] for i in items), 2)
    tax = round(sub * float(tax_percent or 0) / 100, 2)
    return sub, tax, round(sub + tax, 2)


def effective_status(row):
    if row["status"] == "sent" and row["due_date"] and row["due_date"] < today().isoformat():
        return "overdue"
    return row["status"]


def present(row):
    items = json.loads(row["items"] or "[]")
    sub, tax, total = totals(items, row["tax_percent"])
    d = dict(row)
    d.update(items=items, subtotal=sub, tax=tax, total=total, display_status=effective_status(row))
    return d


def next_number(c, uid):
    n = c.execute("SELECT COUNT(*) FROM invoices WHERE user_id=?", (uid,)).fetchone()[0] + 1
    while c.execute("SELECT 1 FROM invoices WHERE user_id=? AND number=?", (uid, f"INV-{n:04d}")).fetchone():
        n += 1
    return f"INV-{n:04d}"


def create_invoice(c, uid, data):
    items = clean_items(data.get("items"))
    status = data.get("status", "draft")
    if status not in ("draft", "sent"):
        raise ValueError("status must be draft or sent when creating")
    issue = today()
    due = data.get("due_date") or (issue + dt.timedelta(days=int(data.get("due_in_days", 14)))).isoformat()
    number = next_number(c, uid)
    c.execute(
        """INSERT INTO invoices(user_id,number,public_id,client_name,client_email,currency,items,tax_percent,
           notes,status,issue_date,due_date,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (uid, number, secrets.token_urlsafe(9), str(data.get("client_name", "")).strip() or "Unnamed client",
         str(data.get("client_email", "")).strip(), str(data.get("currency", "USD")).upper()[:3],
         json.dumps(items), float(data.get("tax_percent", 0) or 0), str(data.get("notes", "")),
         status, issue.isoformat(), due, now(), now()),
    )
    return number


def apply_update(c, uid, number, data):
    row = c.execute("SELECT * FROM invoices WHERE user_id=? AND number=?", (uid, number)).fetchone()
    if not row:
        raise ValueError(f"No invoice {number}")
    fields = {}
    for k in ("client_name", "client_email", "notes", "due_date", "issue_date"):
        if k in data and data[k] is not None:
            fields[k] = str(data[k])
    if "currency" in data and data["currency"]:
        fields["currency"] = str(data["currency"]).upper()[:3]
    if "tax_percent" in data and data["tax_percent"] is not None:
        fields["tax_percent"] = float(data["tax_percent"])
    if "items" in data and data["items"] is not None:
        fields["items"] = json.dumps(clean_items(data["items"]))
    if "due_in_days" in data and data["due_in_days"] is not None:
        fields["due_date"] = (dt.date.fromisoformat(row["issue_date"]) + dt.timedelta(days=int(data["due_in_days"]))).isoformat()
    if "status" in data and data["status"]:
        if data["status"] not in STATUSES:
            raise ValueError(f"status must be one of {', '.join(STATUSES)}")
        fields["status"] = data["status"]
        fields["paid_date"] = today().isoformat() if data["status"] == "paid" else None
    if not fields:
        return
    fields["updated"] = now()
    sets = ", ".join(f"{k}=?" for k in fields)
    c.execute(f"UPDATE invoices SET {sets} WHERE id=?", (*fields.values(), row["id"]))


def summary(c, uid):
    rows = [present(r) for r in c.execute("SELECT * FROM invoices WHERE user_id=?", (uid,))]
    out = {}
    for r in rows:
        if r["status"] == "void":
            continue
        cur = out.setdefault(r["currency"], {"paid": 0, "outstanding": 0, "overdue": 0, "draft": 0})
        s = r["display_status"]
        if s == "paid":
            cur["paid"] += r["total"]
        elif s == "overdue":
            cur["overdue"] += r["total"]
            cur["outstanding"] += r["total"]
        elif s == "sent":
            cur["outstanding"] += r["total"]
        elif s == "draft":
            cur["draft"] += r["total"]
    return {k: {a: round(b, 2) for a, b in v.items()} for k, v in out.items()}


# ----------------------------------------------------------------- web UI
def current_user(request):
    uid = request.session.get("uid")
    if not uid:
        return None
    with db() as c:
        return c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()


def base_url(request):
    return os.environ.get("BASE_URL") or str(request.base_url).rstrip("/")


@app.get("/")
def home(request: Request):
    return RedirectResponse("/dashboard" if request.session.get("uid") else "/login", 303)


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/login")
def login_page(request: Request):
    return render("login.html", request, mode="login", error=None)


@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    with db() as c:
        u = c.execute("SELECT * FROM users WHERE username=?", (username.strip().lower(),)).fetchone()
    if not u or not check_pw(password, u["pw"]):
        return render("login.html", request, mode="login", error="Wrong username or password.")
    request.session["uid"] = u["id"]
    return RedirectResponse("/dashboard", 303)


@app.get("/signup")
def signup_page(request: Request):
    return render("login.html", request, mode="signup", error=None)


@app.post("/signup")
def signup(request: Request, username: str = Form(...), password: str = Form(...)):
    username = username.strip().lower()
    if len(username) < 3 or len(password) < 8:
        return render("login.html", request, mode="signup", error="Username needs 3+ characters and password 8+.")
    try:
        with db() as c:
            cur = c.execute(
                "INSERT INTO users(username,pw,token,created) VALUES(?,?,?,?)",
                (username, hash_pw(password), secrets.token_urlsafe(24), now()),
            )
            uid = cur.lastrowid
    except sqlite3.IntegrityError:
        return render("login.html", request, mode="signup", error="That username is taken.")
    request.session["uid"] = uid
    return RedirectResponse("/dashboard", 303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", 303)


@app.get("/dashboard")
def dashboard(request: Request):
    u = current_user(request)
    if not u:
        return RedirectResponse("/login", 303)
    with db() as c:
        rows = [present(r) for r in c.execute("SELECT * FROM invoices WHERE user_id=? ORDER BY id DESC", (u["id"],))]
        stats = summary(c, u["id"])
    return render("dashboard.html", request, u=u, invoices=rows, stats=stats,
                  mcp_url=f"{base_url(request)}/mcp/{u['token']}")


@app.post("/profile")
def profile(request: Request, business_name: str = Form(""), payment_details: str = Form("")):
    u = current_user(request)
    if not u:
        return RedirectResponse("/login", 303)
    with db() as c:
        c.execute("UPDATE users SET business_name=?, payment_details=? WHERE id=?",
                  (business_name.strip(), payment_details.strip(), u["id"]))
    return RedirectResponse("/dashboard", 303)


@app.get("/invoice/new")
def invoice_new(request: Request):
    u = current_user(request)
    if not u:
        return RedirectResponse("/login", 303)
    with db() as c:
        n = create_invoice(c, u["id"], {"client_name": "New client", "items": [{"description": "Service", "quantity": 1, "unit_price": 0}]})
    return RedirectResponse(f"/invoice/{n}", 303)


@app.get("/invoice/{number}")
def invoice_edit(request: Request, number: str):
    u = current_user(request)
    if not u:
        return RedirectResponse("/login", 303)
    with db() as c:
        r = c.execute("SELECT * FROM invoices WHERE user_id=? AND number=?", (u["id"], number)).fetchone()
    if not r:
        return HTMLResponse("Invoice not found", 404)
    return render("edit.html", request, inv=present(r), u=u, public_url=f"{base_url(request)}/i/{r['public_id']}",
                  saved=request.query_params.get("saved"))


@app.post("/invoice/{number}")
async def invoice_save(request: Request, number: str):
    u = current_user(request)
    if not u:
        return RedirectResponse("/login", 303)
    f = await request.form()
    data = {
        "client_name": f.get("client_name", ""), "client_email": f.get("client_email", ""),
        "currency": f.get("currency", "USD"), "tax_percent": f.get("tax_percent") or 0,
        "issue_date": f.get("issue_date"), "due_date": f.get("due_date"), "notes": f.get("notes", ""),
        "items": json.loads(f.get("items_json") or "[]"),
    }
    if f.get("action") in STATUSES:
        data["status"] = f["action"]
    with db() as c:
        apply_update(c, u["id"], number, data)
    return RedirectResponse(f"/invoice/{number}?saved=1", 303)


@app.post("/invoice/{number}/delete")
def invoice_delete(request: Request, number: str):
    u = current_user(request)
    if not u:
        return RedirectResponse("/login", 303)
    with db() as c:
        c.execute("DELETE FROM invoices WHERE user_id=? AND number=?", (u["id"], number))
    return RedirectResponse("/dashboard", 303)


@app.get("/i/{public_id}")
def public_invoice(request: Request, public_id: str):
    with db() as c:
        r = c.execute("SELECT * FROM invoices WHERE public_id=?", (public_id,)).fetchone()
        if not r or r["status"] == "draft":
            return HTMLResponse("This invoice is not available.", 404)
        owner = c.execute("SELECT * FROM users WHERE id=?", (r["user_id"],)).fetchone()
    return render("public.html", request, inv=present(r), owner=owner)


# --------------------------------------------------------------------- MCP
PROTOCOLS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")

ITEMS_SCHEMA = {
    "type": "array",
    "description": "Line items. Each has description, quantity (default 1) and unit_price (number, no currency symbol).",
    "items": {"type": "object", "properties": {
        "description": {"type": "string"}, "quantity": {"type": "number"}, "unit_price": {"type": "number"}},
        "required": ["description", "unit_price"]},
}
TOOLS = [
    {"name": "create_invoice",
     "description": "Create an invoice in Billed. Returns the invoice number, totals, a link to edit it and a public link to share with the client. Create as draft unless the user says it is ready to send.",
     "inputSchema": {"type": "object", "properties": {
         "client_name": {"type": "string"}, "client_email": {"type": "string"}, "items": ITEMS_SCHEMA,
         "currency": {"type": "string", "description": "3-letter code, e.g. USD, AED, INR"},
         "due_in_days": {"type": "integer", "description": "Days until due. Default 14."},
         "tax_percent": {"type": "number"}, "notes": {"type": "string", "description": "Payment terms or a thank-you line."},
         "status": {"type": "string", "enum": ["draft", "sent"]}},
         "required": ["client_name", "items"]}},
    {"name": "list_invoices",
     "description": "List invoices, newest first. Optionally filter by status (draft, sent, paid, overdue, void) or client name.",
     "inputSchema": {"type": "object", "properties": {"status": {"type": "string"}, "client": {"type": "string"}}}},
    {"name": "get_invoice", "description": "Get one invoice by number, e.g. INV-0003.",
     "inputSchema": {"type": "object", "properties": {"number": {"type": "string"}}, "required": ["number"]}},
    {"name": "update_invoice",
     "description": "Change fields on an existing invoice. Only send the fields that change. Sending items replaces all line items.",
     "inputSchema": {"type": "object", "properties": {
         "number": {"type": "string"}, "client_name": {"type": "string"}, "client_email": {"type": "string"},
         "items": ITEMS_SCHEMA, "currency": {"type": "string"}, "tax_percent": {"type": "number"},
         "notes": {"type": "string"}, "due_date": {"type": "string", "description": "YYYY-MM-DD"},
         "due_in_days": {"type": "integer", "description": "Days after the issue date."}},
         "required": ["number"]}},
    {"name": "set_invoice_status",
     "description": "Mark an invoice as draft, sent, paid or void. A draft invoice has no public link until it is sent.",
     "inputSchema": {"type": "object", "properties": {
         "number": {"type": "string"}, "status": {"type": "string", "enum": list(STATUSES)}},
         "required": ["number", "status"]}},
    {"name": "get_summary",
     "description": "Totals by currency: paid, outstanding, overdue and draft amounts.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "set_business_profile",
     "description": "Set the business name and payment instructions that appear on every invoice.",
     "inputSchema": {"type": "object", "properties": {
         "business_name": {"type": "string"}, "payment_details": {"type": "string", "description": "Bank details, payment link, etc."}}}},
]


def inv_out(r, base):
    d = present(r)
    return {
        "number": d["number"], "client_name": d["client_name"], "client_email": d["client_email"],
        "status": d["display_status"], "currency": d["currency"], "items": d["items"],
        "subtotal": d["subtotal"], "tax": d["tax"], "total": d["total"], "issue_date": d["issue_date"],
        "due_date": d["due_date"], "notes": d["notes"],
        "edit_url": f"{base}/invoice/{d['number']}",
        "public_url": f"{base}/i/{d['public_id']}" + ("" if d["status"] != "draft" else "  (live once status is sent)"),
    }


def run_tool(name, args, user, base):
    uid = user["id"]
    with db() as c:
        if name == "create_invoice":
            n = create_invoice(c, uid, args)
            r = c.execute("SELECT * FROM invoices WHERE user_id=? AND number=?", (uid, n)).fetchone()
            return inv_out(r, base)
        if name == "list_invoices":
            rows = c.execute("SELECT * FROM invoices WHERE user_id=? ORDER BY id DESC", (uid,)).fetchall()
            out = [inv_out(r, base) for r in rows]
            if args.get("status"):
                out = [o for o in out if o["status"] == args["status"]]
            if args.get("client"):
                out = [o for o in out if args["client"].lower() in o["client_name"].lower()]
            return {"count": len(out), "invoices": [{k: o[k] for k in ("number", "client_name", "status", "currency", "total", "due_date")} for o in out]}
        if name in ("get_invoice", "update_invoice", "set_invoice_status"):
            num = str(args.get("number", "")).upper()
            if name != "get_invoice":
                apply_update(c, uid, num, {k: v for k, v in args.items() if k != "number"})
            r = c.execute("SELECT * FROM invoices WHERE user_id=? AND number=?", (uid, num)).fetchone()
            if not r:
                raise ValueError(f"No invoice {num}")
            return inv_out(r, base)
        if name == "get_summary":
            return summary(c, uid)
        if name == "set_business_profile":
            if args.get("business_name") is not None:
                c.execute("UPDATE users SET business_name=? WHERE id=?", (args["business_name"], uid))
            if args.get("payment_details") is not None:
                c.execute("UPDATE users SET payment_details=? WHERE id=?", (args["payment_details"], uid))
            return {"ok": True}
    raise ValueError(f"Unknown tool {name}")


def rpc_handle(msg, user, base):
    mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
    if mid is None:  # notification: no reply
        return None

    def ok(result):
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    def err(code, text):
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": text}}

    if method == "initialize":
        want = params.get("protocolVersion")
        return ok({"protocolVersion": want if want in PROTOCOLS else PROTOCOLS[1],
                   "capabilities": {"tools": {"listChanged": False}},
                   "serverInfo": {"name": "billed", "version": "1.0.0"},
                   "instructions": "Billed stores and serves invoices. Draft invoices with create_invoice, then tell the user the edit link so they can review before sending."})
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": TOOLS})
    if method == "tools/call":
        try:
            res = run_tool(params.get("name"), params.get("arguments") or {}, user, base)
            return ok({"content": [{"type": "text", "text": json.dumps(res, indent=2)}]})
        except Exception as e:  # report tool problems to Claude so it can retry
            return ok({"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True})
    return err(-32601, f"Method not found: {method}")


@app.post("/mcp/{token}")
async def mcp(request: Request, token: str):
    with db() as c:
        user = c.execute("SELECT * FROM users WHERE token=?", (token,)).fetchone()
    if not user:
        return JSONResponse({"error": "invalid token"}, status_code=401)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}, status_code=400)
    base = base_url(request)
    if isinstance(body, list):
        replies = [r for r in (rpc_handle(m, user, base) for m in body) if r]
        return JSONResponse(replies) if replies else Response(status_code=202)
    reply = rpc_handle(body, user, base)
    return JSONResponse(reply) if reply else Response(status_code=202)


@app.get("/mcp/{token}")
def mcp_get(token: str):
    return Response(status_code=405, headers={"Allow": "POST"})

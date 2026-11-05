CSS = """
:root{--ink:#15233b;--bg:#f5f6f8;--card:#fff;--line:#dfe3ea;--muted:#66728a;--green:#137a5a;--amber:#b4551d;--red:#b3261e;--blue:#2447a8}
@media (prefers-color-scheme:dark){:root{--ink:#e8ecf4;--bg:#10151f;--card:#18202e;--line:#2b3548;--muted:#97a3ba;--green:#4cc79b;--amber:#f0a36b;--red:#ff8a80;--blue:#8fb0ff}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 'Instrument Sans',system-ui,sans-serif;font-variant-numeric:tabular-nums}
a{color:var(--blue)}
.wrap{max-width:980px;margin:0 auto;padding:24px 20px 64px}
header.top{display:flex;align-items:center;justify-content:space-between;padding:16px 20px;max-width:980px;margin:0 auto}
header.top b{font-size:20px;letter-spacing:-.02em}
h1{font-size:26px;letter-spacing:-.02em;margin:8px 0 16px}
h2{font-size:17px;margin:0 0 10px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:18px;margin-bottom:18px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:18px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}
.stat span{display:block;color:var(--muted);font-size:14px}.stat strong{font-size:22px}
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:10px 8px;border-bottom:1px solid var(--line);font-size:15px}
th{color:var(--muted);font-weight:500}
td.r,th.r{text-align:right}
.badge{padding:2px 9px;border-radius:99px;font-size:13px;border:1px solid var(--line)}
.paid{color:var(--green);border-color:var(--green)}.overdue{color:var(--red);border-color:var(--red)}
.sent{color:var(--blue);border-color:var(--blue)}.draft,.void{color:var(--muted)}
input,textarea,select{width:100%;padding:9px 10px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink);font:inherit}
input:focus-visible,textarea:focus-visible,select:focus-visible,button:focus-visible,a:focus-visible{outline:2px solid var(--blue);outline-offset:2px}
label{display:block;font-size:14px;color:var(--muted);margin-bottom:4px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}
.btn{display:inline-block;padding:9px 16px;border-radius:8px;border:1px solid var(--ink);background:var(--ink);color:var(--bg);font:inherit;cursor:pointer;text-decoration:none}
.btn.ghost{background:transparent;color:var(--ink);border-color:var(--line)}
.btn.green{background:var(--green);border-color:var(--green);color:#fff}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
code,.mono{background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:2px 6px;word-break:break-all}
.muted{color:var(--muted)}.err{color:var(--red)}.ok{color:var(--green)}
.items input{padding:7px}.items td{border:0;padding:4px}
ol.steps{padding-left:20px;margin:8px 0}
@media (max-width:640px){th,td{font-size:14px;padding:8px 4px}}
"""

HEAD = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{% block title %}Billed{% endblock %}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>""" + CSS + """</style></head><body>"""

TEMPLATES = {
"base.html": HEAD + """
<header class="top"><b>Billed</b>{% if u %}<span class="row"><span class="muted">{{ u.username }}</span><a href="/logout">Log out</a></span>{% endif %}</header>
{% block body %}{% endblock %}</body></html>""",

"login.html": """{% extends "base.html" %}{% block title %}{{ 'Create account' if mode=='signup' else 'Log in' }} · Billed{% endblock %}
{% block body %}<div class="wrap" style="max-width:420px">
<h1>{{ 'Create your account' if mode=='signup' else 'Log in to Billed' }}</h1>
<p class="muted">Invoices written by your own Claude, stored and shared by Billed.</p>
<form class="card" method="post" action="/{{ mode }}">
{% if error %}<p class="err">{{ error }}</p>{% endif %}
<label for="u">Username</label><input id="u" name="username" required autocomplete="username"><br><br>
<label for="p">Password</label><input id="p" name="password" type="password" required autocomplete="current-password"><br><br>
<button class="btn" type="submit">{{ 'Create account' if mode=='signup' else 'Log in' }}</button>
</form>
{% if mode=='signup' %}<a href="/login">I already have an account</a>{% else %}<a href="/signup">Create an account</a>{% endif %}
</div>{% endblock %}""",

"dashboard.html": """{% extends "base.html" %}{% block title %}Invoices · Billed{% endblock %}
{% block body %}<div class="wrap">
<div class="row" style="justify-content:space-between"><h1>Invoices</h1><a class="btn" href="/invoice/new">New invoice</a></div>
{% if stats %}<div class="stats">{% for cur, s in stats.items() %}
<div class="stat"><span>Outstanding ({{ cur }})</span><strong>{{ s.outstanding|money }}</strong></div>
<div class="stat"><span>Overdue ({{ cur }})</span><strong>{{ s.overdue|money }}</strong></div>
<div class="stat"><span>Paid ({{ cur }})</span><strong>{{ s.paid|money }}</strong></div>{% endfor %}</div>{% endif %}
<div class="card">
{% if invoices %}<div style="overflow-x:auto"><table><tr><th>Number</th><th>Client</th><th>Due</th><th>Status</th><th class="r">Total</th></tr>
{% for i in invoices %}<tr><td><a href="/invoice/{{ i.number }}">{{ i.number }}</a></td><td>{{ i.client_name }}</td><td>{{ i.due_date }}</td>
<td><span class="badge {{ i.display_status }}">{{ i.display_status }}</span></td><td class="r">{{ i.currency }} {{ i.total|money }}</td></tr>{% endfor %}</table></div>
{% else %}<p class="muted">No invoices yet. Ask your connected Claude to invoice a client, or click New invoice.</p>{% endif %}
</div>
<div class="card"><h2>Connect your Claude</h2>
<p>Your private MCP link (treat it like a password):</p>
<p><code id="mcp">{{ mcp_url }}</code> <button class="btn ghost" type="button" onclick="navigator.clipboard.writeText(document.getElementById('mcp').textContent);this.textContent='Copied'">Copy</button></p>
<ol class="steps"><li>In Claude, open Settings, then Connectors, then Add custom connector.</li>
<li>Name it Billed and paste the link above. Leave any advanced fields empty.</li>
<li>In a chat, enable Billed and ask: <em>Invoice Acme Ltd for 3 days of design at 500 USD per day, due in 14 days.</em></li></ol></div>
<div class="card"><h2>Your business on every invoice</h2>
<form method="post" action="/profile" class="grid">
<div><label for="bn">Business name</label><input id="bn" name="business_name" value="{{ u.business_name }}"></div>
<div><label for="pd">Payment details</label><textarea id="pd" name="payment_details" rows="3">{{ u.payment_details }}</textarea></div>
<div><button class="btn ghost" type="submit">Save profile</button></div></form></div>
</div>{% endblock %}""",

"edit.html": """{% extends "base.html" %}{% block title %}{{ inv.number }} · Billed{% endblock %}
{% block body %}<div class="wrap">
<p><a href="/dashboard">All invoices</a></p>
<div class="row" style="justify-content:space-between"><h1>{{ inv.number }} <span class="badge {{ inv.display_status }}">{{ inv.display_status }}</span></h1>
{% if inv.status != 'draft' %}<a class="btn ghost" href="{{ public_url }}" target="_blank" rel="noopener">View client page</a>{% endif %}</div>
{% if saved %}<p class="ok" role="status">Saved.</p>{% endif %}
<form method="post" id="f" class="card">
<div class="grid">
<div><label for="cn">Client name</label><input id="cn" name="client_name" value="{{ inv.client_name }}" required></div>
<div><label for="ce">Client email</label><input id="ce" name="client_email" value="{{ inv.client_email }}"></div>
<div><label for="cu">Currency</label><input id="cu" name="currency" maxlength="3" value="{{ inv.currency }}"></div>
<div><label for="tx">Tax %</label><input id="tx" name="tax_percent" type="number" step="0.01" min="0" value="{{ inv.tax_percent }}"></div>
<div><label for="id">Issue date</label><input id="id" name="issue_date" type="date" value="{{ inv.issue_date }}"></div>
<div><label for="dd">Due date</label><input id="dd" name="due_date" type="date" value="{{ inv.due_date }}"></div></div>
<h2 style="margin-top:18px">Line items</h2>
<div style="overflow-x:auto"><table class="items"><thead><tr><th>Description</th><th style="width:90px">Qty</th><th style="width:130px">Unit price</th><th class="r" style="width:110px">Amount</th><th style="width:40px"></th></tr></thead><tbody id="rows"></tbody></table></div>
<button class="btn ghost" type="button" id="add">Add line</button>
<p class="r" style="text-align:right;margin:12px 0 0">Subtotal <b id="sub"></b><br>Tax <b id="tax"></b><br>Total <b id="tot" style="font-size:20px"></b></p>
<label for="nt" style="margin-top:12px">Notes</label><textarea id="nt" name="notes" rows="3">{{ inv.notes }}</textarea>
<input type="hidden" name="items_json" id="ij">
<div class="row" style="margin-top:16px">
<button class="btn" name="action" value="save" type="submit">Save changes</button>
{% if inv.status == 'draft' %}<button class="btn" name="action" value="sent" type="submit">Save and send</button>{% endif %}
{% if inv.status != 'paid' %}<button class="btn green" name="action" value="paid" type="submit">Mark paid</button>{% endif %}
{% if inv.status != 'void' %}<button class="btn ghost" name="action" value="void" type="submit">Void</button>{% endif %}
</div></form>
<form method="post" action="/invoice/{{ inv.number }}/delete" onsubmit="return confirm('Delete {{ inv.number }}? This cannot be undone.')"><button class="btn ghost" type="submit">Delete invoice</button></form>
</div>
<script>
const items={{ inv['items']|tojson }};const rows=document.getElementById('rows');
const fmt=n=>(Math.round(n*100)/100).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
function row(it){const tr=document.createElement('tr');
tr.innerHTML='<td><input class="d" aria-label="Description"></td><td><input class="q" type="number" step="any" min="0" aria-label="Quantity"></td><td><input class="p" type="number" step="any" min="0" aria-label="Unit price"></td><td class="r a"></td><td><button type="button" class="btn ghost" aria-label="Remove line" style="padding:4px 9px">x</button></td>';
tr.querySelector('.d').value=it.description||'';tr.querySelector('.q').value=it.quantity??1;tr.querySelector('.p').value=it.unit_price??0;
tr.querySelectorAll('input').forEach(i=>i.addEventListener('input',calc));tr.querySelector('button').onclick=()=>{tr.remove();calc()};rows.appendChild(tr);}
function collect(){return [...rows.children].map(r=>({description:r.querySelector('.d').value,quantity:parseFloat(r.querySelector('.q').value)||0,unit_price:parseFloat(r.querySelector('.p').value)||0}));}
function calc(){let s=0;[...rows.children].forEach(r=>{const a=(parseFloat(r.querySelector('.q').value)||0)*(parseFloat(r.querySelector('.p').value)||0);r.querySelector('.a').textContent=fmt(a);s+=a});
const t=s*(parseFloat(document.getElementById('tx').value)||0)/100;sub.textContent=fmt(s);tax.textContent=fmt(t);tot.textContent=fmt(s+t);}
items.forEach(row);document.getElementById('add').onclick=()=>{row({});calc()};document.getElementById('tx').addEventListener('input',calc);
document.getElementById('f').addEventListener('submit',()=>{document.getElementById('ij').value=JSON.stringify(collect())});calc();
</script>{% endblock %}""",

"public.html": HEAD + """
<style>body{background:var(--bg)}.sheet{max-width:780px;margin:32px auto;background:#fff;color:#15233b;border:1px solid #dfe3ea;border-radius:6px;padding:44px}
.sheet th,.sheet td{border-bottom:1px solid #e6e9ef;color:#15233b}.sheet .muted{color:#66728a}
.big{font-size:34px;letter-spacing:-.03em;font-weight:700;margin:0}
.stamp{display:inline-block;border:2px solid #137a5a;color:#137a5a;padding:2px 12px;border-radius:4px;font-weight:700;transform:rotate(-4deg)}
@media print{body{background:#fff}.sheet{border:0;margin:0;padding:0}.noprint{display:none}}</style>
<div class="sheet">
<div class="row" style="justify-content:space-between;align-items:flex-start">
<div><p class="big">Invoice</p><p class="muted">{{ inv.number }}</p></div>
<div style="text-align:right"><b>{{ owner.business_name or owner.username }}</b></div></div>
<div class="grid" style="margin:26px 0"><div><span class="muted">Billed to</span><br><b>{{ inv.client_name }}</b><br>{{ inv.client_email }}</div>
<div><span class="muted">Issued</span><br>{{ inv.issue_date }}</div>
<div><span class="muted">Due</span><br>{{ inv.due_date }}</div>
<div>{% if inv.status=='paid' %}<span class="stamp">PAID</span>{% elif inv.status=='void' %}<span class="muted">Void</span>{% elif inv.display_status=='overdue' %}<b style="color:#b3261e">Overdue</b>{% endif %}</div></div>
<table><tr><th>Description</th><th class="r">Qty</th><th class="r">Unit price</th><th class="r">Amount</th></tr>
{% for it in inv['items'] %}<tr><td>{{ it.description }}</td><td class="r">{{ it.quantity|round(2) }}</td><td class="r">{{ it.unit_price|money }}</td><td class="r">{{ (it.quantity*it.unit_price)|money }}</td></tr>{% endfor %}</table>
<p style="text-align:right;margin-top:16px"><span class="muted">Subtotal</span> {{ inv.subtotal|money }}<br>{% if inv.tax_percent %}<span class="muted">Tax {{ inv.tax_percent }}%</span> {{ inv.tax|money }}<br>{% endif %}
<span style="font-size:24px;font-weight:700">{{ inv.currency }} {{ inv.total|money }}</span></p>
{% if inv.notes %}<p class="muted" style="white-space:pre-wrap">{{ inv.notes }}</p>{% endif %}
{% if owner.payment_details %}<p><b>How to pay</b><br><span style="white-space:pre-wrap">{{ owner.payment_details }}</span></p>{% endif %}
<p class="noprint"><button class="btn" onclick="window.print()">Print or save as PDF</button></p></div></body></html>""",
}

"""Server-rendered UI (English). Industrial-catalogue look: graphite rail, steel surface, cobalt accent."""
import html
import json
import traceback
from urllib.parse import urlencode

from starlette.responses import HTMLResponse, RedirectResponse
from starlette.routing import Route
from starlette.concurrency import run_in_threadpool

from . import store, schema

FONTS = '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,400..800&display=swap" rel="stylesheet">'

CSS = """
:root{--bp:#0E2A47;--bp2:#123457;--grid:rgba(160,200,240,.10);--grid2:rgba(160,200,240,.05);--line:#7FB2E5;--paper:#FBFCFD;--ink:#0D1B2A;--mute:#5B6B7C;--rule:#D5DEE8;--rule2:#E8EEF4;
--orange:#FF6A1A;--orange-soft:#FFE9DC;--blue:#1F5FBF;--blue-soft:#E3EDFA;--teal:#0F7F6B;--teal-soft:#DDF2EC;--rust:#B23A1F;--rust-soft:#F8E1DA;--violet:#5B47B8;--violet-soft:#ECE8F8;--on-bp:#E8F1FB;--on-bp-mute:#9DB6D0}
*{box-sizing:border-box}
html{background:var(--bp)}
body{margin:0;min-height:100vh;color:var(--ink);font-family:Archivo,"Helvetica Neue",Arial,sans-serif;font-size:14px;line-height:1.45;font-variation-settings:"wdth" 100;
background-color:var(--bp);background-image:linear-gradient(var(--grid) 1px,transparent 1px),linear-gradient(90deg,var(--grid) 1px,transparent 1px),linear-gradient(var(--grid2) 1px,transparent 1px),linear-gradient(90deg,var(--grid2) 1px,transparent 1px);
background-size:120px 120px,120px 120px,24px 24px,24px 24px;background-attachment:fixed}
a{color:var(--blue);text-decoration:none}a:hover{text-decoration:underline}
:focus-visible{outline:2px solid var(--orange);outline-offset:2px}
.top{position:sticky;top:0;z-index:20;display:flex;align-items:flex-end;gap:26px;padding:14px 32px 0;background:linear-gradient(var(--bp) 70%,rgba(14,42,71,.92));border-bottom:1px solid rgba(127,178,229,.35);flex-wrap:wrap}
.brand{display:flex;align-items:center;gap:11px;color:#fff;padding-bottom:12px}
.mark{width:36px;height:36px;border:1.5px solid var(--line);display:grid;place-items:center;font-weight:800;font-variation-settings:"wdth" 125;font-size:14px;color:#fff;position:relative}
.mark::after{content:"";position:absolute;inset:3px;border:1px dashed rgba(127,178,229,.55)}
.brand b{font-size:16px;font-variation-settings:"wdth" 118;line-height:1.05;font-weight:780}.brand small{display:block;color:var(--on-bp-mute);font-weight:400;font-size:12px}
.tabs{display:flex;gap:2px;flex-wrap:wrap}
.tabs a{color:var(--on-bp-mute);padding:9px 14px 10px;border:1px solid transparent;border-bottom:0;font-weight:550;border-radius:6px 6px 0 0}
.tabs a:hover{color:#fff;text-decoration:none;background:rgba(127,178,229,.10)}
.tabs a.on{color:var(--ink);background:var(--paper);border-color:var(--paper);font-weight:700}
main{padding:30px 32px 130px;max-width:1480px;margin:0 auto}
.head{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;flex-wrap:wrap;margin-bottom:20px}
h1{font-size:36px;line-height:1.05;margin:0;font-weight:800;font-variation-settings:"wdth" 122;letter-spacing:-.4px;color:#fff}
.sub{color:var(--on-bp-mute);margin-top:8px;max-width:76ch}
h2{font-size:15px;margin:28px 0 10px;font-weight:700;font-variation-settings:"wdth" 112;color:var(--on-bp)}
h2::before{content:"";display:inline-block;width:18px;height:1px;background:var(--line);vertical-align:middle;margin-right:10px}
.panel{background:var(--paper);border:1px solid var(--rule);border-radius:4px}
.pad{padding:16px 18px}
table{width:100%;border-collapse:collapse;background:var(--paper);border-radius:4px;overflow:hidden;box-shadow:0 0 0 1px rgba(127,178,229,.45)}
th,td{text-align:left;padding:10px 12px;border-bottom:1px solid var(--rule2);vertical-align:top}
th{background:#F1F5F9;font-weight:650;color:var(--mute);font-size:12.5px;border-bottom:1px solid var(--rule)}
tbody tr:hover td{background:#F5F9FD}
tr:last-child td{border-bottom:0}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}.date{white-space:nowrap;color:var(--mute)}
td.name a,td.name{font-weight:600;color:var(--ink)}td.name a:hover{color:var(--blue)}
.muted{color:var(--mute)}.small{font-size:12.5px}
.pill{display:inline-block;padding:2px 9px;border-radius:3px;font-size:12px;font-weight:650;background:var(--rule2);color:var(--mute);white-space:nowrap}
.pill.blue{background:var(--blue-soft);color:var(--blue)}.pill.amber{background:var(--orange-soft);color:#A6400A}.pill.teal{background:var(--teal-soft);color:var(--teal)}
.pill.rust{background:var(--rust-soft);color:var(--rust)}.pill.violet{background:var(--violet-soft);color:var(--violet)}
.cls{display:inline-grid;place-items:center;width:26px;height:26px;font-weight:800;font-variation-settings:"wdth" 122;font-size:13px;border:1.5px solid}
.cls.A{background:var(--orange);color:#fff;border-color:var(--orange)}.cls.B{background:#fff;color:var(--blue);border-color:var(--blue)}.cls.C{background:#fff;color:var(--mute);border-color:#AAB6C3}
form.bar,.bar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:16px}
input,select{padding:10px 12px;border:1px solid var(--rule);border-radius:4px;font:inherit;background:#fff;color:var(--ink);min-width:0}
input:focus,select:focus{border-color:var(--orange);outline:none;box-shadow:0 0 0 3px rgba(255,106,26,.25)}
button,.btn{padding:10px 18px;border:0;border-radius:4px;background:var(--orange);color:#fff;font:inherit;font-weight:700;cursor:pointer}
button:hover,.btn:hover{filter:brightness(1.05);text-decoration:none}
button.ghost,.btn.ghost{background:transparent;color:var(--on-bp);border:1px solid rgba(127,178,229,.6)}
.chips{display:flex;gap:6px;flex-wrap:wrap}.chip{padding:7px 13px;border-radius:3px;border:1px solid rgba(127,178,229,.55);color:var(--on-bp);font-weight:550}
.chip.on{background:var(--paper);color:var(--ink);border-color:var(--paper);font-weight:700}.chip:hover{text-decoration:none;border-color:#fff;color:#fff}.chip.on:hover{color:var(--ink)}
.pager{margin-top:14px;display:flex;gap:12px;align-items:center;color:var(--on-bp-mute)}.pager .muted{color:var(--on-bp-mute)}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:0;border:1px solid rgba(127,178,229,.5)}
.stat{padding:18px 20px;border-right:1px solid rgba(127,178,229,.35);color:var(--on-bp);position:relative}.stat:last-child{border-right:0}
.stat:hover{background:rgba(127,178,229,.08);text-decoration:none}
.stat .v{font-size:34px;font-weight:800;font-variation-settings:"wdth" 120;font-variant-numeric:tabular-nums;line-height:1.1;color:#fff}
.stat .l{color:var(--on-bp-mute);font-size:13px;margin-top:4px}
.stat.hot .v{color:var(--orange)}
.classbar{display:flex;height:14px;overflow:hidden;background:var(--rule2);margin:10px 0 8px}
.classbar span{display:block}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:13px;color:var(--mute)}.legend i{display:inline-block;width:10px;height:10px;margin-right:6px;vertical-align:-1px}
.grid2{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(0,1fr);gap:24px}
/* title block (cartiglio) */
.tb{display:grid;grid-template-columns:minmax(0,2.3fr) minmax(0,1.1fr) minmax(0,1.1fr) 150px;grid-template-areas:"name name name cls" "rev vat code cls" "city web web rel";
background:var(--paper);border:2px solid var(--ink);margin-bottom:24px;box-shadow:8px 8px 0 rgba(0,0,0,.18)}
.tb>div{padding:10px 14px;border-right:1px solid var(--ink);border-bottom:1px solid var(--ink);min-width:0}
.tb .k{font-size:11.5px;color:var(--mute);margin-bottom:3px}.tb .v{font-weight:650;overflow-wrap:anywhere}
.tb .name{grid-area:name;padding:16px 18px}.tb .name h1{color:var(--ink);font-size:34px}
.tb .cls-cell{grid-area:cls;border-right:0;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;background:#F3F6FA}
.tb .cls-cell .letter{font-size:84px;line-height:.9;font-weight:800;font-variation-settings:"wdth" 125;color:var(--ink)}
.tb .cls-cell.A{background:var(--orange)}.tb .cls-cell.A .letter,.tb .cls-cell.A .k{color:#fff}
.tb .cls-cell.none .letter{color:#AAB6C3;font-size:56px}
.tb .rev{grid-area:rev}.tb .rev .v{font-size:24px;font-weight:800;font-variation-settings:"wdth" 115;font-variant-numeric:tabular-nums}
.tb .vat{grid-area:vat}.tb .code{grid-area:code}.tb .city{grid-area:city;border-bottom:0}.tb .web{grid-area:web;border-bottom:0}.tb .rel{grid-area:rel;border-right:0;border-bottom:0;background:#F3F6FA}
.tb .note{grid-column:1/-1;border-right:0;border-bottom:0;border-top:1px solid var(--ink);font-size:12.5px;color:var(--mute)}
/* timeline */
.tl{list-style:none;margin:0;padding:4px 0}
.tl li{position:relative;padding:10px 16px 10px 34px;border-bottom:1px solid var(--rule2)}.tl li:last-child{border-bottom:0}
.tl li::before{content:"";position:absolute;left:14px;top:15px;width:9px;height:9px;background:var(--blue)}
.tl li.calls::before{background:var(--teal)}.tl li.emails::before{background:var(--violet)}.tl li.meetings::before{background:var(--orange)}.tl li.tasks::before{background:var(--rust);border-radius:50%}
.tl .k{font-size:12.5px;color:var(--mute);margin-bottom:2px}.tl .t{white-space:pre-wrap}
/* board */
.board{display:flex;gap:12px;overflow-x:auto;padding-bottom:12px;align-items:flex-start}
.col{min-width:254px;flex:1;background:rgba(232,241,251,.07);border:1px solid rgba(127,178,229,.4);border-top:4px solid var(--c,#9AA4AE);padding:10px}
.col h3{margin:2px 2px 10px;font-size:14px;font-weight:700;display:flex;justify-content:space-between;align-items:baseline;font-variation-settings:"wdth" 110;color:#fff}
.col h3 span.n{font-variant-numeric:tabular-nums;color:var(--on-bp-mute);font-weight:600}
.card{background:var(--paper);border-radius:3px;padding:10px 11px;margin-bottom:8px;border-left:3px solid var(--c,#9AA4AE)}
.card .t{font-weight:650;line-height:1.3}.card .amt{font-weight:800;font-variant-numeric:tabular-nums;margin-top:6px;font-variation-settings:"wdth" 110}.card .m{color:var(--mute);font-size:12.5px;margin-top:2px;overflow-wrap:anywhere}
.more{font-size:12.5px;color:var(--on-bp-mute);padding:4px 2px}
/* chat */
#chat{height:58vh;overflow-y:auto;background:var(--paper);border-radius:4px;padding:18px;box-shadow:0 0 0 1px rgba(127,178,229,.45)}
.msg{margin:10px 0;max-width:78%;padding:10px 14px;border-radius:4px;white-space:pre-wrap;line-height:1.5}
.msg.u{background:var(--bp2);color:#fff;margin-left:auto}.msg.a{background:#EEF3F8;border-left:3px solid var(--orange)}
label.muted,.bar .muted{color:var(--on-bp-mute)}
/* AI dock */
.dock{position:fixed;left:50%;bottom:18px;transform:translateX(-50%);width:min(780px,calc(100vw - 32px));z-index:30;display:flex;gap:8px;align-items:center;padding:8px 8px 8px 16px;
background:rgba(9,28,48,.94);border:1px solid rgba(127,178,229,.6);border-radius:8px;box-shadow:0 14px 40px rgba(0,0,0,.35);backdrop-filter:blur(6px)}
.dock span{color:var(--orange);font-weight:800;font-variation-settings:"wdth" 118;white-space:nowrap}
.dock input{flex:1;background:transparent;border:0;color:#fff;font-size:15px;padding:10px 6px}.dock input::placeholder{color:var(--on-bp-mute)}
.dock input:focus{box-shadow:none}
.empty{padding:36px;text-align:center;color:var(--mute)}
.err{background:var(--rust-soft);color:var(--rust);border:1px solid #EBC3B6;border-radius:4px;padding:14px;white-space:pre-wrap;font-size:12.5px}
@media(max-width:900px){.top{padding:12px 16px 0;gap:10px}.tabs a{padding:7px 9px 8px}main{padding:20px 16px 120px}main table{display:block;overflow-x:auto}.grid2{grid-template-columns:1fr}
h1{font-size:27px}.tb{grid-template-columns:1fr 1fr;grid-template-areas:"name name" "cls rev" "vat code" "city web" "rel rel"}.tb>div{border-right:1px solid var(--ink)}.tb .name h1{font-size:26px}.tb .rev .v{font-size:18px;overflow-wrap:normal}.tb .cls-cell .letter{font-size:60px}.dock span{display:none}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
"""

NAV = [("", "Overview"), ("companies", "Companies"), ("contacts", "Contacts"), ("deals", "Deals board"), ("tickets", "Tickets"),
       ("dormant", "Dormant customers"), ("products", "Price list"), ("assistant", "Assistant")]


def page(title, body, on=""):
    nav = "".join(f'<a class="{"on" if k == on else ""}" href="/{k}">{l}</a>' for k, l in NAV)
    dock = "" if on == "assistant" else '<form class="dock" action="/assistant" method="get"><span>Ask the CRM</span><input name="q" placeholder="Es. Quali sono i miei clienti di classe A? Segna come vinta la trattativa di…" aria-label="Ask the assistant"><button>Ask</button></form>'
    return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)} · Brambilla CRM</title>{FONTS}<style>{CSS}</style></head><body>
<header class="top"><a class="brand" href="/" style="text-decoration:none"><div class="mark">BF</div><b>Brambilla CRM<small>Forniture industriali</small></b></a><nav class="tabs">{nav}</nav></header>
<main>{body}</main>{dock}</body></html>""")


def safe(fn):
    """Render any page error inline instead of a blank 500, so problems are visible."""
    async def wrapped(req):
        try:
            return await fn(req)
        except Exception:
            return page("Error", f'<div class="head"><div><h1>This page could not load</h1><div class="sub">The API is not affected. Details:</div></div></div><div class="err">{html.escape(traceback.format_exc())}</div>')
    wrapped.__name__ = fn.__name__
    return wrapped


def e(v):
    return html.escape(str(v)) if v not in (None, "") else '<span class="muted">—</span>'


def money(v, cur="EUR", dash=True):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return '<span class="muted">—</span>' if dash else ""
    s = f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    sym = {"EUR": "€", "USD": "$", "GBP": "£"}.get(cur or "EUR", cur or "")
    return f"{sym} {s}"


def money_short(x):
    x = float(x or 0)
    if abs(x) >= 1_000_000:
        return "€ " + f"{x / 1_000_000:,.1f}".replace(".", ",") + " M"
    if abs(x) >= 1000:
        return "€ " + f"{x / 1000:,.0f}".replace(",", ".") + " k"
    return money(x)


def clsbadge(c):
    return f'<span class="cls {html.escape(c)}">{html.escape(c)}</span>' if c in ("A", "B", "C") else ""


def stage_labels():
    m = {}
    for t in ("deals", "tickets"):
        for p in store.pipelines(t):
            for s in p["stages"]:
                m[(p["id"], s["id"])] = s["label"]
    return m


TICKET_TONE = {"aperto": "blue", "new": "blue", "in lavorazione": "amber", "in attesa del cliente": "violet", "chiuso": "", "closed": ""}
DEAL_TONE = {"closedwon": "teal", "closedlost": "rust"}


def stage_pill(label, tone=None):
    if label is None:
        return '<span class="muted">—</span>'
    tone = tone if tone is not None else TICKET_TONE.get(str(label).lower(), "blue")
    return f'<span class="pill {tone}">{html.escape(str(label))}</span>'


def deal_stage_pill(p, sl):
    label = sl.get((p.get("pipeline"), p.get("dealstage")))
    st = p.get("dealstage")
    tone = DEAL_TONE.get(st)
    if tone is None:
        l = (label or "").lower()
        tone = "teal" if l == "rinnovato" else "rust" if l == "non rinnovato" else "blue"
    return stage_pill(label, tone)


def pager(req, total, after, nxt, noun="records"):
    q = dict(req.query_params)
    shown_to = min(after + 50, total)
    out = f'<div class="pager"><span class="muted">{after + 1 if total else 0}–{shown_to} of {total:,} {noun}</span>'.replace(",", ".")
    if after:
        q2 = dict(q)
        q2["after"] = max(0, after - 50)
        out += f'<a class="btn ghost" href="?{urlencode(q2)}">Previous</a>'
    if nxt:
        q["after"] = nxt
        out += f'<a class="btn ghost" href="?{urlencode(q)}">Next</a>'
    return out + "</div>"


def _search(t, q, filters=None, limit=50, after=0, sorts=None):
    body = {"limit": limit, "after": after}
    if q:
        body["query"] = q
    if filters:
        body["filterGroups"] = [{"filters": filters}]
    if sorts:
        body["sorts"] = sorts
    return store.search(t, body)


def _int(v):
    try:
        return max(0, int(v or 0))
    except ValueError:
        return 0


# ------------------------------------------------------------------ overview
@safe
async def overview(req):
    def work():
        c = store.rconn()
        counts = dict(c.execute("SELECT type, count(*) FROM objects WHERE archived=0 GROUP BY type").fetchall())
        if not counts.get("companies"):
            return page("Overview", """<div class="head"><div><h1>Brambilla CRM</h1><div class="sub">No data yet.</div></div></div>
<div class="panel empty">The CRM is empty. Run the Sinergia migration (<code>POST /__migrate</code>) to load companies, contacts, deals and history.</div>""", "")
        rev_total = c.execute("SELECT sum(CAST(json_extract(props,'$.fatturato_2025') AS REAL)) FROM objects WHERE type='companies' AND archived=0").fetchone()[0] or 0
        cls = dict(c.execute("SELECT json_extract(props,'$.classe_cliente'), count(*) FROM objects WHERE type='companies' AND archived=0 AND json_extract(props,'$.classe_cliente') IS NOT NULL GROUP BY 1").fetchall())
        open_deals = c.execute("SELECT count(*) FROM objects WHERE type='deals' AND archived=0 AND json_extract(props,'$.dealstage') NOT IN ('closedwon','closedlost') AND json_extract(props,'$.pipeline')='default'").fetchone()[0]
        ass = store.pipeline_by_label("tickets", "Assistenza")
        closed_ids = [s["id"] for s in (ass or {}).get("stages", []) if s["metadata"].get("isClosed") == "true"] or ["4"]
        open_tk = c.execute(f"SELECT count(*) FROM objects WHERE type='tickets' AND archived=0 AND json_extract(props,'$.hs_pipeline_stage') NOT IN ({','.join('?' * len(closed_ids))})", closed_ids).fetchone()[0]
        dormant = 0
        for (js,) in c.execute("SELECT json FROM lists"):
            l = json.loads(js)
            if l["name"].lower() == "clienti dormienti":
                dormant = c.execute("SELECT count(*) FROM list_members WHERE list_id=?", (int(l["listId"]),)).fetchone()[0]
        total_cls = sum(cls.values()) or 1
        bar = "".join(f'<span style="width:{cls.get(k, 0) / total_cls * 100:.2f}%;background:{col}"></span>' for k, col in (("A", "var(--orange)"), ("B", "var(--blue)"), ("C", "#9AA4AE")))
        legend = "".join(f'<span><i style="background:{col}"></i>Class {k}: {cls.get(k, 0)}</span>' for k, col in (("A", "var(--orange)"), ("B", "var(--blue)"), ("C", "#9AA4AE")))
        _, top, _ = _search("companies", None, [{"propertyName": "classe_cliente", "operator": "HAS_PROPERTY"}], 10, 0, [{"propertyName": "fatturato_2025", "direction": "DESCENDING"}])
        rows = "".join(f'<tr><td class="name"><a href="/companies/{o["id"]}">{e(o["props"].get("name"))}</a><div class="muted small">{e(o["props"].get("city"))}</div></td><td>{clsbadge(o["props"].get("classe_cliente"))}</td><td class="num">{money(o["props"].get("fatturato_2025"))}</td></tr>' for o in top)
        n = lambda k: f"{counts.get(k, 0):,}".replace(",", ".")
        acts = sum(counts.get(k, 0) for k in ("notes", "calls", "emails", "meetings"))
        body = f"""<div class="head"><div><h1>Brambilla Forniture, at a glance</h1><div class="sub">Customers, pipeline and support after the move from Sinergia 4. Ask the assistant at the bottom of any page.</div></div>
<form class="bar" action="/companies"><input name="q" placeholder="Find a company…" style="width:260px"><button>Search</button></form></div>
<div class="stats">
<a class="stat hot" href="/companies?sort=rev"><div class="v">{money_short(rev_total)}</div><div class="l">Revenue won in 2025</div></a>
<a class="stat" href="/companies"><div class="v">{n('companies')}</div><div class="l">Companies</div></a>
<a class="stat" href="/deals"><div class="v">{f"{open_deals:,}".replace(",", ".")}</div><div class="l">Open sales deals</div></a>
<a class="stat" href="/tickets"><div class="v">{f"{open_tk:,}".replace(",", ".")}</div><div class="l">Open support tickets</div></a>
<a class="stat" href="/dormant"><div class="v">{dormant}</div><div class="l">Dormant customers</div></a>
</div>
<div class="grid2" style="margin-top:22px"><div><h2>Top customers by 2025 revenue</h2><table><thead><tr><th>Company</th><th>Class</th><th class="num">2025 revenue</th></tr></thead><tbody>{rows}</tbody></table></div>
<div><h2>Customer classes</h2><div class="panel pad"><div class="muted small">{total_cls} companies with revenue in 2025 (A from € 100.000, B from € 20.000)</div><div class="classbar">{bar}</div><div class="legend">{legend}</div></div>
<h2>Records in the CRM</h2><div class="panel pad"><table style="border:0"><tbody>
<tr><td>Contacts</td><td class="num">{n('contacts')}</td></tr><tr><td>Deals</td><td class="num">{n('deals')}</td></tr>
<tr><td>Quote lines</td><td class="num">{n('line_items')}</td></tr><tr><td>Products</td><td class="num">{n('products')}</td></tr>
<tr><td>Tickets</td><td class="num">{n('tickets')}</td></tr><tr><td>Activities</td><td class="num">{f"{acts:,}".replace(",", ".")}</td></tr></tbody></table></div></div></div>"""
        return page("Overview", body, "")
    return await run_in_threadpool(work)


# ------------------------------------------------------------------ companies
@safe
async def companies(req):
    def work():
        q = req.query_params.get("q", "")
        cls = req.query_params.get("class", "")
        after = _int(req.query_params.get("after"))
        f = [{"propertyName": "classe_cliente", "operator": "EQ", "value": cls}] if cls in ("A", "B", "C") else None
        by_rev = bool(f) or req.query_params.get("sort") == "rev"
        sorts = [{"propertyName": "fatturato_2025", "direction": "DESCENDING"}] if by_rev else None
        total, objs, nxt = _search("companies", q, f, 50, after, sorts)
        rows = []
        for o in objs:
            p = o["props"]
            rows.append(f"""<tr><td class="name"><a href="/companies/{o['id']}">{e(p.get('name'))}</a><div class="muted small">{e(p.get('domain'))}</div></td>
<td>{e(p.get('city'))} <span class="muted">{html.escape(p.get('state') or '')}</span></td><td class="muted">{e(p.get('partita_iva'))}</td>
<td class="num">{money(p.get('fatturato_2025'))}</td><td>{clsbadge(p.get('classe_cliente'))}</td></tr>""")
        base = {"q": q} if q else {}
        chips = f'<a class="chip {"on" if not cls and not by_rev else ""}" href="?{urlencode(base)}">All</a>'
        chips += f'<a class="chip {"on" if by_rev and not cls else ""}" href="?{urlencode(dict(base, sort="rev"))}">Top revenue 2025</a>'
        for c in ("A", "B", "C"):
            chips += f'<a class="chip {"on" if cls == c else ""}" href="?{urlencode(dict(base, **{"class": c}))}">Class {c}</a>'
        table = f'<table><thead><tr><th>Company</th><th>City</th><th>VAT number</th><th class="num">2025 revenue</th><th>Class</th></tr></thead><tbody>{"".join(rows)}</tbody></table>' if rows else '<div class="panel empty">No companies match this search.</div>'
        return page("Companies", f"""<div class="head"><div><h1>Companies</h1><div class="sub">Every customer once: duplicates from Sinergia merged by website and VAT number.</div></div></div>
<form class="bar"><input name="q" placeholder="Name, domain or city" value="{html.escape(q)}" style="width:300px"><button>Search</button><div class="chips" style="margin-left:6px">{chips}</div></form>
{table}{pager(req, total, after, nxt, "companies")}""", "companies")
    return await run_in_threadpool(work)


def _assoc_objs(oid, t, limit=200):
    out = []
    for i, _ in store.get_assocs(oid, t)[:limit]:
        o = store.get_obj(t, i)
        if o:
            out.append(o)
    return out


@safe
async def company(req):
    def work():
        c = store.get_obj("companies", req.path_params["id"])
        if not c:
            return page("Not found", '<div class="panel empty">This company does not exist or was merged into another one. <a href="/companies">Back to companies</a></div>', "companies")
        p = c["props"]
        sl = stage_labels()
        contacts = _assoc_objs(c["id"], "contacts")
        deals = _assoc_objs(c["id"], "deals")
        deals.sort(key=lambda d: d["props"].get("closedate") or "", reverse=True)
        tickets = _assoc_objs(c["id"], "tickets")
        tickets.sort(key=lambda d: d["props"].get("createdate") or "", reverse=True)
        acts, seen = [], set()
        for src in [c] + contacts[:40] + deals[:40]:
            for at in ("notes", "calls", "emails", "meetings", "tasks"):
                for i, _ in store.get_assocs(src["id"], at)[:30]:
                    if i in seen:
                        continue
                    seen.add(i)
                    o = store.get_obj(at, i)
                    if o:
                        acts.append((at, o))
        acts.sort(key=lambda x: x[1]["props"].get("hs_timestamp") or "", reverse=True)
        cls = p.get("classe_cliente")
        rev = p.get("fatturato_2025")
        cls_cell = f"""<div class="cls-cell {html.escape(cls) if cls else 'none'}"><div class="k">Class</div><div class="letter">{html.escape(cls) if cls else '–'}</div></div>"""
        domains = e(p.get("domain"))
        if p.get("hs_additional_domains"):
            domains += ' <span class="muted small">also ' + html.escape(p["hs_additional_domains"].replace(";", ", ")) + "</span>"
        who = f"""<div class="tb"><div class="name"><div class="k">Company</div><h1>{e(p.get('name'))}</h1></div>{cls_cell}
<div class="rev"><div class="k">Revenue won in 2025</div><div class="v">{money(rev) if rev not in (None, '') else '€ 0,00'}</div></div>
<div class="vat"><div class="k">VAT number</div><div class="v">{e(p.get('partita_iva'))}</div></div>
<div class="code"><div class="k">Sinergia code</div><div class="v">{e(p.get('id_legacy'))}</div></div>
<div class="city"><div class="k">City</div><div class="v">{e(p.get('city'))} {html.escape(p.get('state') or '')}</div></div>
<div class="web"><div class="k">Website</div><div class="v">{domains}</div></div>
<div class="rel"><div class="k">Contacts, deals, tickets</div><div class="v">{len(contacts)} · {len(deals)} · {len(tickets)}</div></div>
{('<div class="note">' + html.escape(p['description']) + '</div>') if p.get('description') else ''}</div>"""
        plate = ""
        crow = "".join(f"<tr><td class='name'>{e(o['props'].get('firstname'))} {e(o['props'].get('lastname'))}</td><td>{e(o['props'].get('email'))}</td><td class='muted'>{e(o['props'].get('phone'))}</td><td>{stage_pill(o['props'].get('lifecyclestage'), '')}</td></tr>" for o in contacts)
        drow = "".join(f"<tr><td class='name'>{e(o['props'].get('dealname'))}</td><td>{deal_stage_pill(o['props'], sl)}</td><td class='num'>{money(o['props'].get('amount'), o['props'].get('deal_currency_code'))}</td><td class='date'>{e((o['props'].get('closedate') or '')[:10])}</td><td class='muted small'>{e(o['props'].get('commerciale'))}</td></tr>" for o in deals)
        trow = "".join(f"<tr><td>{e(o['props'].get('subject'))}</td><td>{stage_pill(sl.get((o['props'].get('hs_pipeline'), o['props'].get('hs_pipeline_stage'))))}</td><td class='muted'>{e(o['props'].get('hs_ticket_priority'))}</td><td class='date'>{e((o['props'].get('createdate') or '')[:10])}</td></tr>" for o in tickets)
        body_k = {"notes": "hs_note_body", "calls": "hs_call_body", "emails": "hs_email_text", "meetings": "hs_meeting_body", "tasks": "hs_task_subject"}
        kind = {"notes": "Note", "calls": "Call", "emails": "Email", "meetings": "Meeting", "tasks": "Task"}
        tl = "".join(f"<li class='{at}'><div class='k'>{kind[at]}, {html.escape((o['props'].get('hs_timestamp') or '')[:16].replace('T', ' '))}{(', ' + html.escape(o['props']['autore'])) if o['props'].get('autore') else ''}</div><div class='t'>{e(o['props'].get(body_k[at]))}</div></li>" for at, o in acts[:60])
        empty = lambda w: f'<div class="panel empty">No {w} yet.</div>'
        return page(p.get("name") or "Company", f"""<div class="small" style="margin-bottom:12px"><a href="/companies" style="color:var(--on-bp-mute)">Companies</a></div>
{who}
<div class="grid2"><div>
<h2>Deals</h2>{('<table><thead><tr><th>Deal</th><th>Stage</th><th class="num">Amount</th><th>Close date</th><th>Sales rep</th></tr></thead><tbody>' + drow + '</tbody></table>') if deals else empty('deals')}
<h2>Contacts</h2>{('<table><thead><tr><th>Name</th><th>Email</th><th>Phone</th><th>Stage</th></tr></thead><tbody>' + crow + '</tbody></table>') if contacts else empty('contacts')}
<h2>Support tickets</h2>{('<table><thead><tr><th>Subject</th><th>Status</th><th>Priority</th><th>Opened</th></tr></thead><tbody>' + trow + '</tbody></table>') if tickets else empty('tickets')}
</div><div><h2>History</h2><div class="panel"><ul class="tl">{tl or '<li class="muted">No activity recorded</li>'}</ul></div></div></div>""", "companies")
    return await run_in_threadpool(work)


@safe
async def contacts(req):
    def work():
        q = req.query_params.get("q", "")
        after = _int(req.query_params.get("after"))
        total, objs, nxt = _search("contacts", q, None, 50, after)
        rows = "".join(f"<tr><td class='name'>{e(o['props'].get('firstname'))} {e(o['props'].get('lastname'))}</td><td>{e(o['props'].get('email'))}</td><td class='muted'>{e(o['props'].get('phone'))}</td><td>{stage_pill(o['props'].get('lifecyclestage'), '')}</td><td>{('<a href=/companies/' + o['props']['associatedcompanyid'] + '>Open company</a>') if o['props'].get('associatedcompanyid') else '<span class=muted>No company</span>'}</td></tr>" for o in objs)
        table = f'<table><thead><tr><th>Name</th><th>Email</th><th>Phone</th><th>Lifecycle</th><th>Company</th></tr></thead><tbody>{rows}</tbody></table>' if rows else '<div class="panel empty">No contacts match this search.</div>'
        return page("Contacts", f"""<div class="head"><div><h1>Contacts</h1><div class="sub">One person, one record. Contacts without a company are linked to it from their email domain.</div></div></div>
<form class="bar"><input name="q" placeholder="Name, email or phone" value="{html.escape(q)}" style="width:300px"><button>Search</button></form>{table}{pager(req, total, after, nxt, "contacts")}""", "contacts")
    return await run_in_threadpool(work)


STAGE_COLORS = ["#9AA4AE", "#7D93C9", "#5C7FDB", "#3E66DD", "#2B54D9", "#11806A", "#B4472A"]


@safe
async def deals(req):
    def work():
        pls = store.pipelines("deals")
        pid = req.query_params.get("pipeline") or "default"
        q = req.query_params.get("q", "")
        owner = req.query_params.get("owner", "")
        pl = store.pipeline_get("deals", pid) or pls[0]
        cols = ""
        n = len(pl["stages"])
        for i, s in enumerate(pl["stages"]):
            f = [{"propertyName": "pipeline", "operator": "EQ", "value": pl["id"]}, {"propertyName": "dealstage", "operator": "EQ", "value": s["id"]}]
            if owner:
                f.append({"propertyName": "commerciale", "operator": "EQ", "value": owner})
            total, objs, _ = _search("deals", q, f, 25, 0, [{"propertyName": "closedate", "direction": "DESCENDING"}])
            lab = s["label"].lower()
            color = "#11806A" if s["id"] == "closedwon" or lab == "rinnovato" else "#B4472A" if s["id"] == "closedlost" or lab == "non rinnovato" else STAGE_COLORS[min(i, 4) if n > 4 else i]
            cards = "".join(f"<div class='card' style='--c:{color}'><div class='t'>{e(o['props'].get('dealname'))}</div><div class='amt'>{money(o['props'].get('amount'), o['props'].get('deal_currency_code'))}</div><div class='m'>{e((o['props'].get('closedate') or '')[:10])}<br>{e(o['props'].get('commerciale'))}</div></div>" for o in objs)
            more = f'<div class="more">and {total - len(objs):,} more</div>'.replace(",", ".") if total > len(objs) else ""
            cols += f"<div class='col' style='--c:{color}'><h3><span>{e(s['label'])}</span><span class='n'>{total:,}</span></h3>{cards or '<div class=more>Nothing here</div>'}{more}</div>".replace(f">{total:,}<", f">{total:,}<".replace(",", "."))
        tabs = "".join(f'<a class="chip {"on" if p["id"] == pl["id"] else ""}" href="?{urlencode({"pipeline": p["id"]})}">{html.escape("Sales" if p["id"] == "default" else p["label"])}</a>' for p in pls)
        return page("Deals", f"""<div class="head"><div><h1>Deals board</h1><div class="sub">Most recent deals in each stage. Winning a sales deal opens a supply kickoff ticket; losing one schedules a call back in six months.</div></div><div class="chips">{tabs}</div></div>
<form class="bar"><input type="hidden" name="pipeline" value="{html.escape(pl['id'])}"><input name="q" placeholder="Deal title" value="{html.escape(q)}" style="width:240px"><input name="owner" placeholder="Sales rep email" value="{html.escape(owner)}" style="width:260px"><button>Filter</button></form>
<div class="board">{cols}</div>""", "deals")
    return await run_in_threadpool(work)


@safe
async def tickets(req):
    def work():
        q = req.query_params.get("q", "")
        stage = req.query_params.get("stage", "")
        after = _int(req.query_params.get("after"))
        sl = stage_labels()
        pl = store.pipeline_by_label("tickets", "Assistenza") or store.pipelines("tickets")[0]
        f = [{"propertyName": "hs_pipeline_stage", "operator": "EQ", "value": stage}] if stage else None
        total, objs, nxt = _search("tickets", q, f, 50, after, [{"propertyName": "createdate", "direction": "DESCENDING"}])
        rows = "".join(f"<tr><td class='name'>{e(o['props'].get('subject'))}</td><td>{stage_pill(sl.get((o['props'].get('hs_pipeline'), o['props'].get('hs_pipeline_stage'))))}</td><td class='muted'>{e(o['props'].get('hs_ticket_priority'))}</td><td class='small'>{e(o['props'].get('assegnatario'))}</td><td class='date'>{e((o['props'].get('createdate') or '')[:10])}</td><td class='date'>{e((o['props'].get('closed_date') or '')[:10])}</td></tr>" for o in objs)
        base = {"q": q} if q else {}
        chips = f'<a class="chip {"on" if not stage else ""}" href="?{urlencode(base)}">All</a>' + "".join(f'<a class="chip {"on" if s["id"] == stage else ""}" href="?{urlencode(dict(base, stage=s["id"]))}">{html.escape(s["label"])}</a>' for s in pl["stages"])
        table = f'<table><thead><tr><th>Subject</th><th>Status</th><th>Priority</th><th>Assignee</th><th>Opened</th><th>Closed</th></tr></thead><tbody>{rows}</tbody></table>' if rows else '<div class="panel empty">No tickets in this view.</div>'
        return page("Tickets", f"""<div class="head"><div><h1>Support tickets</h1><div class="sub">The Assistenza pipeline, newest first.</div></div></div>
<form class="bar"><input name="q" placeholder="Subject or text" value="{html.escape(q)}" style="width:280px"><button>Search</button><div class="chips" style="margin-left:6px">{chips}</div></form>
{table}{pager(req, total, after, nxt, "tickets")}""", "tickets")
    return await run_in_threadpool(work)


@safe
async def dormant(req):
    def work():
        lid = None
        for (js,) in store.rconn().execute("SELECT json FROM lists"):
            l = json.loads(js)
            if l["name"].lower() == "clienti dormienti":
                lid = int(l["listId"])
        ids = [r[0] for r in store.rconn().execute("SELECT obj_id FROM list_members WHERE list_id=? ORDER BY obj_id", (lid or -1,))]
        rows = ""
        for i in ids[:1000]:
            o = store.get_obj("companies", i)
            if o:
                rows += f"<tr><td class='name'><a href='/companies/{o['id']}'>{e(o['props'].get('name'))}</a></td><td>{e(o['props'].get('city'))}</td><td class='muted'>{e(o['props'].get('domain'))}</td></tr>"
        table = f"<table><thead><tr><th>Company</th><th>City</th><th>Website</th></tr></thead><tbody>{rows}</tbody></table>" if rows else '<div class="panel empty">No dormant customers: every customer with a won deal had activity in 2025.</div>'
        return page("Dormant customers", f"""<div class="head"><div><h1>Dormant customers</h1><div class="sub">{len(ids)} companies won at least one deal but had no calls, emails, meetings or notes in 2025. Worth a call.</div></div></div>{table}""", "dormant")
    return await run_in_threadpool(work)


@safe
async def products(req):
    def work():
        q = req.query_params.get("q", "")
        after = _int(req.query_params.get("after"))
        total, objs, nxt = _search("products", q, None, 50, after)
        rows = "".join(f"<tr><td class='muted'>{e(o['props'].get('hs_sku'))}</td><td class='name'>{e(o['props'].get('name'))}</td><td class='num'>{money(o['props'].get('price'))}</td></tr>" for o in objs)
        table = f"<table><thead><tr><th>Code</th><th>Description</th><th class='num'>Price</th></tr></thead><tbody>{rows}</tbody></table>" if rows else '<div class="panel empty">No products match this search.</div>'
        return page("Price list", f"""<div class="head"><div><h1>Price list</h1><div class="sub">Current price of every article, codes normalised to BF-00000.</div></div></div>
<form class="bar"><input name="q" placeholder="Code or description" value="{html.escape(q)}" style="width:280px"><button>Search</button></form>{table}{pager(req, total, after, nxt, "products")}""", "products")
    return await run_in_threadpool(work)


_ui_calls = []


async def ui_agent(req):
    import time as _t
    from . import agent
    from starlette.responses import JSONResponse
    now = _t.time()
    _ui_calls[:] = [x for x in _ui_calls if now - x < 3600]
    if len(_ui_calls) >= 60:
        return JSONResponse({"reply": "Too many assistant requests from the web UI in the last hour, try again later."}, 429)
    _ui_calls.append(now)
    try:
        body = await req.json()
    except Exception:
        return JSONResponse({"reply": "Invalid request"}, 400)
    reply = await run_in_threadpool(agent.run, body)
    return JSONResponse({"reply": reply})


@safe
async def assistant(req):
    def users():
        out = []
        for (js,) in store.rconn().execute("SELECT json FROM owners ORDER BY id"):
            o = json.loads(js)
            if not o.get("archived"):
                out.append(o)
        return out
    us = await run_in_threadpool(users)
    opts = "".join(f'<option value="{html.escape(o["email"])}">{html.escape(o["firstName"] + " " + o["lastName"])} ({html.escape(o["email"])})</option>' for o in us)
    if not opts:
        opts = '<option value="">No users yet: run the migration first</option>'
    return page("Assistant", f"""<div class="head"><div><h1>Assistant</h1><div class="sub">Write in Italian, as you would to a colleague. It reads and updates the CRM, and asks when a request is ambiguous.</div></div></div>
<div class="bar" style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;align-items:center"><label for="user" class="muted">Writing as</label><select id="user" style="min-width:340px">{opts}</select></div>
<div id="chat"></div><form id="f" class="bar" style="margin-top:12px"><input id="m" style="flex:1;min-width:260px" placeholder="Es. Quanto abbiamo fatturato con Officine Farina di Lecco nel 2025?"><button>Send</button><button type="button" id="clr" class="ghost">New chat</button></form>
<script>
let msgs=[];const chat=document.getElementById('chat');
try{{const u=localStorage.getItem('user');if(u)user.value=u}}catch(e){{}}
function esc(t){{return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}}
function md(t){{return esc(t).replace(/\\*\\*(.+?)\\*\\*/g,'<b>$1</b>').replace(/(^|\\n)[-*] /g,'$1• ')}}
function save(){{try{{sessionStorage.setItem('chat',JSON.stringify(msgs))}}catch(e){{}}}}
function add(r,t){{const d=document.createElement('div');d.className='msg '+(r=='user'?'u':'a');if(r=='user')d.textContent=t;else d.innerHTML=md(t);chat.appendChild(d);chat.scrollTop=1e9}}
f.onsubmit=async ev=>{{ev.preventDefault();const t=m.value.trim();if(!t)return;m.value='';try{{localStorage.setItem('user',user.value)}}catch(e){{}}
msgs.push({{role:'user',content:t}});add('user',t);add('assistant','Working on it…');
const r=await fetch('/ui/agent',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{context:{{now:new Date().toISOString(),user:user.value}},messages:msgs}})}});
const j=await r.json().catch(()=>({{reply:'Error '+r.status}}));chat.lastChild.remove();const rep=j.reply||('Error '+r.status);msgs.push({{role:'assistant',content:rep}});add('assistant',rep);save()}}
clr.onclick=()=>{{msgs=[];save();chat.innerHTML=''}};
try{{msgs=JSON.parse(sessionStorage.getItem('chat')||'[]');msgs.forEach(x=>add(x.role,x.content))}}catch(e){{msgs=[]}}
const q0=new URLSearchParams(location.search).get('q');if(q0){{m.value=q0;history.replaceState(null,'','/assistant');f.requestSubmit()}}
</script>""", "assistant")


def routes():
    return [Route("/", overview), Route("/overview", overview), Route("/companies", companies), Route("/companies/{id}", company),
            Route("/contacts", contacts), Route("/deals", deals), Route("/tickets", tickets), Route("/dormant", dormant),
            Route("/products", products), Route("/assistant", assistant), Route("/ui/agent", ui_agent, methods=["POST"])]

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
:root{--graphite:#1F252B;--graphite2:#2A3239;--steel:#EDEFF2;--paper:#FFFFFF;--ink:#14191E;--mute:#5E6873;--line:#D3D8DE;--line2:#E6E9ED;
--cobalt:#2B54D9;--cobalt-soft:#E6ECFC;--amber:#E0A100;--amber-soft:#FCF3D9;--teal:#11806A;--teal-soft:#DDF2EC;--rust:#B4472A;--rust-soft:#F8E4DD;--violet:#6A4BC4;--violet-soft:#ECE7F9}
*{box-sizing:border-box}
html,body{margin:0;background:var(--steel);color:var(--ink)}
body{font-family:Archivo,"Helvetica Neue",Arial,sans-serif;font-size:14px;line-height:1.45;font-variation-settings:"wdth" 100;display:grid;grid-template-columns:232px 1fr;min-height:100vh}
a{color:var(--cobalt);text-decoration:none}a:hover{text-decoration:underline}
:focus-visible{outline:2px solid var(--cobalt);outline-offset:2px}
.rail{background:var(--graphite);color:#C9D1D9;padding:22px 14px;position:sticky;top:0;height:100vh;display:flex;flex-direction:column;gap:22px}
.brand{display:flex;align-items:center;gap:10px;padding:0 8px;color:#fff}
.mark{width:34px;height:34px;border-radius:7px;background:var(--cobalt);display:grid;place-items:center;font-weight:800;font-variation-settings:"wdth" 125;font-size:14px;letter-spacing:.5px}
.brand b{font-size:15px;font-variation-settings:"wdth" 112;line-height:1.1}.brand small{display:block;color:#8D98A3;font-weight:400;font-size:12px}
.rail nav{display:flex;flex-direction:column;gap:2px}
.rail nav a{color:#C9D1D9;padding:8px 10px;border-radius:6px;border-left:3px solid transparent;font-weight:500}
.rail nav a:hover{background:var(--graphite2);text-decoration:none;color:#fff}
.rail nav a.on{background:var(--graphite2);color:#fff;border-left-color:var(--cobalt);font-weight:650}
.rail .foot{margin-top:auto;font-size:12px;color:#7D8893;padding:0 8px}
main{padding:30px 34px 60px;min-width:0;max-width:1440px}
.head{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;flex-wrap:wrap;margin-bottom:18px}
h1{font-size:30px;line-height:1.1;margin:0;font-weight:780;font-variation-settings:"wdth" 118;letter-spacing:-.3px}
.sub{color:var(--mute);margin-top:6px}
h2{font-size:16px;margin:28px 0 10px;font-weight:700;font-variation-settings:"wdth" 110}
.panel{background:var(--paper);border:1px solid var(--line);border-radius:10px}
.pad{padding:16px 18px}
table{width:100%;border-collapse:collapse;background:var(--paper);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{text-align:left;padding:10px 12px;border-bottom:1px solid var(--line2);vertical-align:top}
th{background:#F6F7F9;font-weight:600;color:var(--mute);font-size:12.5px}
tbody tr:hover td{background:#F8F9FB}
tr:last-child td{border-bottom:0}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}.date{white-space:nowrap;color:var(--mute)}
td.name a{font-weight:600;color:var(--ink)}td.name a:hover{color:var(--cobalt)}
.muted{color:var(--mute)}.small{font-size:12.5px}
.pill{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px;font-weight:600;background:var(--line2);color:var(--mute);white-space:nowrap}
.pill.blue{background:var(--cobalt-soft);color:var(--cobalt)}.pill.amber{background:var(--amber-soft);color:#8A6200}.pill.teal{background:var(--teal-soft);color:var(--teal)}
.pill.rust{background:var(--rust-soft);color:var(--rust)}.pill.violet{background:var(--violet-soft);color:var(--violet)}
.cls{display:inline-grid;place-items:center;width:26px;height:26px;border-radius:5px;font-weight:800;font-variation-settings:"wdth" 120;font-size:13px;border:1.5px solid}
.cls.A{background:var(--amber-soft);color:#7A5600;border-color:var(--amber)}.cls.B{background:var(--cobalt-soft);color:var(--cobalt);border-color:#9DB2F2}.cls.C{background:#F1F3F5;color:var(--mute);border-color:var(--line)}
form.bar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:16px}
input,select{padding:9px 12px;border:1px solid var(--line);border-radius:8px;font:inherit;background:#fff;color:var(--ink);min-width:0}
input:focus,select:focus{border-color:var(--cobalt);outline:none;box-shadow:0 0 0 3px var(--cobalt-soft)}
button,.btn{padding:9px 16px;border:0;border-radius:8px;background:var(--cobalt);color:#fff;font:inherit;font-weight:600;cursor:pointer}
button.ghost,.btn.ghost{background:#fff;color:var(--ink);border:1px solid var(--line)}
.chips{display:flex;gap:6px;flex-wrap:wrap}.chip{padding:6px 12px;border-radius:999px;border:1px solid var(--line);background:#fff;color:var(--ink);font-weight:500}
.chip.on{background:var(--graphite);color:#fff;border-color:var(--graphite)}.chip:hover{text-decoration:none;border-color:var(--cobalt)}
.pager{margin-top:12px;display:flex;gap:14px;align-items:center}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}
.stat{background:var(--paper);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.stat .v{font-size:26px;font-weight:780;font-variation-settings:"wdth" 118;font-variant-numeric:tabular-nums;line-height:1.15}
.stat .l{color:var(--mute);font-size:13px}
.classbar{display:flex;height:12px;border-radius:6px;overflow:hidden;background:var(--line2);margin:10px 0 8px}
.classbar span{display:block}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:13px;color:var(--mute)}.legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px;vertical-align:-1px}
.grid2{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(0,1fr);gap:22px}
/* company hero */
.hero{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:20px;align-items:stretch;margin-bottom:20px}
.hero .who{background:var(--paper);border:1px solid var(--line);border-radius:12px;padding:20px 22px}
.hero h1{font-size:34px}
.facts{display:flex;gap:22px;flex-wrap:wrap;margin-top:14px;color:var(--mute)}.facts b{display:block;color:var(--ink);font-weight:600}
.plate{position:relative;width:300px;border-radius:12px;padding:18px 22px;background:linear-gradient(160deg,#3A434C,#232A31);color:#E9EDF1;display:flex;gap:18px;align-items:center;box-shadow:inset 0 1px 0 rgba(255,255,255,.08)}
.plate::before,.plate::after,.plate .s1,.plate .s2{content:"";position:absolute;width:7px;height:7px;border-radius:50%;background:radial-gradient(circle at 35% 35%,#C8CFD6,#6F7983)}
.plate::before{top:9px;left:9px}.plate::after{top:9px;right:9px}.plate .s1{bottom:9px;left:9px}.plate .s2{bottom:9px;right:9px}
.plate .letter{font-size:72px;line-height:.9;font-weight:800;font-variation-settings:"wdth" 125;color:#fff}
.plate.A .letter{color:var(--amber)}.plate.none .letter{color:#7D8893;font-size:48px}
.plate .rev{font-size:24px;font-weight:760;font-variation-settings:"wdth" 115;font-variant-numeric:tabular-nums}
.plate .cap{font-size:12.5px;color:#AEB7C0}
/* timeline */
.tl{list-style:none;margin:0;padding:6px 0 6px 0}
.tl li{position:relative;padding:10px 16px 10px 34px;border-bottom:1px solid var(--line2)}.tl li:last-child{border-bottom:0}
.tl li::before{content:"";position:absolute;left:14px;top:16px;width:9px;height:9px;border-radius:50%;background:var(--cobalt)}
.tl li.calls::before{background:var(--teal)}.tl li.emails::before{background:var(--violet)}.tl li.meetings::before{background:var(--amber)}.tl li.tasks::before{background:var(--rust)}
.tl .k{font-size:12.5px;color:var(--mute);margin-bottom:2px}.tl .t{white-space:pre-wrap}
/* board */
.board{display:flex;gap:12px;overflow-x:auto;padding-bottom:12px;align-items:flex-start}
.col{min-width:252px;flex:1;background:#E3E6EA;border-radius:10px;padding:10px;border-top:4px solid var(--c,#9AA4AE)}
.col h3{margin:2px 2px 10px;font-size:14px;font-weight:700;display:flex;justify-content:space-between;align-items:baseline;font-variation-settings:"wdth" 108}
.col h3 span.n{font-variant-numeric:tabular-nums;color:var(--mute);font-weight:600}
.card{background:#fff;border:1px solid var(--line);border-radius:8px;padding:10px 11px;margin-bottom:8px}
.card .t{font-weight:600;line-height:1.3}.card .amt{font-weight:700;font-variant-numeric:tabular-nums;margin-top:6px}.card .m{color:var(--mute);font-size:12.5px;margin-top:2px;overflow-wrap:anywhere}
.more{font-size:12.5px;color:var(--mute);padding:4px 2px}
/* chat */
#chat{height:60vh;overflow-y:auto;background:var(--paper);border:1px solid var(--line);border-radius:12px;padding:18px}
.msg{margin:10px 0;max-width:78%;padding:10px 14px;border-radius:12px;white-space:pre-wrap;line-height:1.5}
.msg.u{background:var(--cobalt);color:#fff;margin-left:auto;border-bottom-right-radius:4px}.msg.a{background:#F1F3F6;border-bottom-left-radius:4px}
.empty{padding:36px;text-align:center;color:var(--mute)}
.err{background:var(--rust-soft);color:var(--rust);border:1px solid #EBC3B6;border-radius:10px;padding:14px;white-space:pre-wrap;font-size:12.5px}
@media(max-width:980px){body{grid-template-columns:1fr}.rail{position:static;height:auto;flex-direction:row;flex-wrap:wrap;align-items:center;padding:12px 16px;gap:12px}
.rail nav{flex-direction:row;flex-wrap:wrap}.rail nav a{border-left:0;border-bottom:3px solid transparent;padding:6px 8px}.rail nav a.on{border-bottom-color:var(--cobalt)}.rail .foot{display:none}
main{padding:20px 16px 40px}main table{display:block;overflow-x:auto}.grid2,.hero{grid-template-columns:1fr}.plate{width:auto}h1{font-size:25px}.hero h1{font-size:27px}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
"""

NAV = [("", "Overview"), ("companies", "Companies"), ("contacts", "Contacts"), ("deals", "Deals board"), ("tickets", "Tickets"),
       ("dormant", "Dormant customers"), ("products", "Price list"), ("assistant", "Assistant")]


def page(title, body, on=""):
    nav = "".join(f'<a class="{"on" if k == on else ""}" href="/{k}">{l}</a>' for k, l in NAV)
    return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)} · Brambilla CRM</title>{FONTS}<style>{CSS}</style></head><body>
<aside class="rail"><div class="brand"><div class="mark">BF</div><b>Brambilla CRM<small>Forniture industriali</small></b></div><nav>{nav}</nav>
<div class="foot">Migrated from Sinergia 4</div></aside><main>{body}</main></body></html>""")


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
        bar = "".join(f'<span style="width:{cls.get(k, 0) / total_cls * 100:.2f}%;background:{col}"></span>' for k, col in (("A", "var(--amber)"), ("B", "var(--cobalt)"), ("C", "#9AA4AE")))
        legend = "".join(f'<span><i style="background:{col}"></i>Class {k}: {cls.get(k, 0)}</span>' for k, col in (("A", "var(--amber)"), ("B", "var(--cobalt)"), ("C", "#9AA4AE")))
        _, top, _ = _search("companies", None, [{"propertyName": "classe_cliente", "operator": "HAS_PROPERTY"}], 10, 0, [{"propertyName": "fatturato_2025", "direction": "DESCENDING"}])
        rows = "".join(f'<tr><td class="name"><a href="/companies/{o["id"]}">{e(o["props"].get("name"))}</a><div class="muted small">{e(o["props"].get("city"))}</div></td><td>{clsbadge(o["props"].get("classe_cliente"))}</td><td class="num">{money(o["props"].get("fatturato_2025"))}</td></tr>' for o in top)
        n = lambda k: f"{counts.get(k, 0):,}".replace(",", ".")
        acts = sum(counts.get(k, 0) for k in ("notes", "calls", "emails", "meetings"))
        body = f"""<div class="head"><div><h1>Good to see you</h1><div class="sub">Brambilla Forniture at a glance: customers, pipeline and support, after the move from Sinergia 4.</div></div>
<form class="bar" action="/companies"><input name="q" placeholder="Find a company…" style="width:260px"><button>Search</button></form></div>
<div class="stats">
<a class="stat" href="/companies?sort=rev"><div class="v">{money_short(rev_total)}</div><div class="l">Revenue won in 2025</div></a>
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
        plate = f"""<div class="plate {html.escape(cls) if cls else 'none'}"><span class="s1"></span><span class="s2"></span>
<div class="letter">{html.escape(cls) if cls else '–'}</div><div><div class="cap">{'Class ' + html.escape(cls) if cls else 'No class'}</div><div class="rev">{money(rev) if rev not in (None, '') else '€ 0,00'}</div><div class="cap">revenue won in 2025</div></div></div>"""
        domains = e(p.get("domain"))
        if p.get("hs_additional_domains"):
            domains += ' <span class="muted small">also ' + html.escape(p["hs_additional_domains"].replace(";", ", ")) + "</span>"
        who = f"""<div class="who"><h1>{e(p.get('name'))}</h1><div class="facts">
<div><span>Website</span><b>{domains}</b></div><div><span>City</span><b>{e(p.get('city'))} {html.escape(p.get('state') or '')}</b></div>
<div><span>VAT number</span><b>{e(p.get('partita_iva'))}</b></div><div><span>Sinergia code</span><b>{e(p.get('id_legacy'))}</b></div>
<div><span>Contacts · Deals · Tickets</span><b>{len(contacts)} · {len(deals)} · {len(tickets)}</b></div></div>
{('<div class="muted small" style="margin-top:12px">' + html.escape(p['description']) + '</div>') if p.get('description') else ''}</div>"""
        crow = "".join(f"<tr><td class='name'>{e(o['props'].get('firstname'))} {e(o['props'].get('lastname'))}</td><td>{e(o['props'].get('email'))}</td><td class='muted'>{e(o['props'].get('phone'))}</td><td>{stage_pill(o['props'].get('lifecyclestage'), '')}</td></tr>" for o in contacts)
        drow = "".join(f"<tr><td class='name'>{e(o['props'].get('dealname'))}</td><td>{deal_stage_pill(o['props'], sl)}</td><td class='num'>{money(o['props'].get('amount'), o['props'].get('deal_currency_code'))}</td><td class='date'>{e((o['props'].get('closedate') or '')[:10])}</td><td class='muted small'>{e(o['props'].get('commerciale'))}</td></tr>" for o in deals)
        trow = "".join(f"<tr><td>{e(o['props'].get('subject'))}</td><td>{stage_pill(sl.get((o['props'].get('hs_pipeline'), o['props'].get('hs_pipeline_stage'))))}</td><td class='muted'>{e(o['props'].get('hs_ticket_priority'))}</td><td class='date'>{e((o['props'].get('createdate') or '')[:10])}</td></tr>" for o in tickets)
        body_k = {"notes": "hs_note_body", "calls": "hs_call_body", "emails": "hs_email_text", "meetings": "hs_meeting_body", "tasks": "hs_task_subject"}
        kind = {"notes": "Note", "calls": "Call", "emails": "Email", "meetings": "Meeting", "tasks": "Task"}
        tl = "".join(f"<li class='{at}'><div class='k'>{kind[at]}, {html.escape((o['props'].get('hs_timestamp') or '')[:16].replace('T', ' '))}{(', ' + html.escape(o['props']['autore'])) if o['props'].get('autore') else ''}</div><div class='t'>{e(o['props'].get(body_k[at]))}</div></li>" for at, o in acts[:60])
        empty = lambda w: f'<div class="panel empty">No {w} yet.</div>'
        return page(p.get("name") or "Company", f"""<div class="small" style="margin-bottom:10px"><a href="/companies">Companies</a></div>
<div class="hero">{who}{plate}</div>
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
            cards = "".join(f"<div class='card'><div class='t'>{e(o['props'].get('dealname'))}</div><div class='amt'>{money(o['props'].get('amount'), o['props'].get('deal_currency_code'))}</div><div class='m'>{e((o['props'].get('closedate') or '')[:10])}<br>{e(o['props'].get('commerciale'))}</div></div>" for o in objs)
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
</script>""", "assistant")


def routes():
    return [Route("/", overview), Route("/overview", overview), Route("/companies", companies), Route("/companies/{id}", company),
            Route("/contacts", contacts), Route("/deals", deals), Route("/tickets", tickets), Route("/dormant", dormant),
            Route("/products", products), Route("/assistant", assistant), Route("/ui/agent", ui_agent, methods=["POST"])]

"""Server-rendered UI (English). Dark dashboard look: sidebar, KPI cards, area chart, activity rail."""
import html
import json
import time
import traceback
from urllib.parse import urlencode, quote

from starlette.responses import HTMLResponse, RedirectResponse
from starlette.routing import Route
from starlette.concurrency import run_in_threadpool

from . import store, schema

FONTS = '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap" rel="stylesheet">'

CSS = """
:root{--bg:#0B0B10;--side:#111118;--card:#17171F;--card2:#1E1E28;--line:#262631;--ink:#EDEDF3;--mute:#8C8C9C;--purple:#7C5CFF;--purple-soft:rgba(124,92,255,.16);
--green:#34D399;--green-soft:rgba(52,211,153,.14);--red:#F87171;--red-soft:rgba(248,113,113,.14);--yellow:#FBBF24;--yellow-soft:rgba(251,191,36,.14);--blue:#60A5FA;--blue-soft:rgba(96,165,250,.14);--pink:#F472B6}
*{box-sizing:border-box}
html,body{margin:0;background:var(--bg);color:var(--ink)}
body{font-family:Poppins,"Helvetica Neue",Arial,sans-serif;font-size:14px;line-height:1.5;display:grid;grid-template-columns:240px 1fr;min-height:100vh}
a{color:#B7A6FF;text-decoration:none}a:hover{text-decoration:underline}
:focus-visible{outline:2px solid var(--purple);outline-offset:2px}
.side{background:var(--side);padding:26px 16px;position:sticky;top:0;height:100vh;display:flex;flex-direction:column;gap:26px;border-right:1px solid var(--line)}
.brand{display:flex;align-items:center;gap:10px;padding:0 10px;color:#fff;text-decoration:none}.brand:hover{text-decoration:none}
.mark{width:36px;height:36px;border-radius:10px;background:linear-gradient(135deg,var(--purple),#A78BFA);display:grid;place-items:center;font-weight:700;font-size:13px}
.brand b{font-size:15px;font-weight:600;line-height:1.15}.brand small{display:block;color:var(--mute);font-weight:400;font-size:11.5px}
.nav{display:flex;flex-direction:column;gap:4px}
.nav a{display:flex;align-items:center;gap:12px;color:var(--mute);padding:10px 14px;border-radius:10px;font-weight:500}
.nav a svg{width:18px;height:18px;flex:none;stroke:currentColor;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
.nav a:hover{background:var(--card);color:var(--ink);text-decoration:none}
.nav a.on{background:var(--purple);color:#fff;font-weight:600;box-shadow:0 8px 22px rgba(124,92,255,.35)}
.side .foot{margin-top:auto;font-size:12px;color:#5E5E6C;padding:0 12px;border-top:1px solid var(--line);padding-top:16px}
main{padding:30px 34px 130px;min-width:0;max-width:1500px}
.head{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;margin-bottom:24px}
h1{font-size:28px;line-height:1.15;margin:0;font-weight:600;color:#fff}
.sub{color:var(--mute);margin-top:4px;font-size:13.5px}
h2{font-size:17px;margin:0 0 14px;font-weight:600;color:#fff}
section.blk{margin-top:26px}
.panel{background:var(--card);border-radius:18px;border:1px solid var(--line)}
.pad{padding:20px 22px}
table{width:100%;border-collapse:separate;border-spacing:0;background:var(--card);border-radius:18px;overflow:hidden;border:1px solid var(--line)}
th,td{text-align:left;padding:12px 16px;border-bottom:1px solid var(--line);vertical-align:top}
th{background:var(--card2);font-weight:500;color:var(--mute);font-size:12.5px}
tbody tr:hover td{background:#1C1C26}
tr:last-child td{border-bottom:0}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}.date{white-space:nowrap;color:var(--mute)}
td.name a,td.name{font-weight:500;color:var(--ink)}td.name a:hover{color:#B7A6FF}
.muted{color:var(--mute)}.small{font-size:12.5px}
.pill{display:inline-block;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:500;background:#2A2A35;color:var(--mute);white-space:nowrap}
.pill.blue{background:var(--blue-soft);color:var(--blue)}.pill.amber{background:var(--yellow-soft);color:var(--yellow)}.pill.teal{background:var(--green-soft);color:var(--green)}
.pill.rust{background:var(--red-soft);color:var(--red)}.pill.violet{background:var(--purple-soft);color:#B7A6FF}
.cls{display:inline-grid;place-items:center;width:28px;height:28px;border-radius:8px;font-weight:700;font-size:13px}
.cls.A{background:var(--yellow-soft);color:var(--yellow)}.cls.B{background:var(--purple-soft);color:#B7A6FF}.cls.C{background:#2A2A35;color:var(--mute)}
form.bar,.bar{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:18px}
input,select{padding:11px 16px;border:1px solid var(--line);border-radius:12px;font:inherit;background:var(--card);color:var(--ink);min-width:0}
input::placeholder{color:#6B6B7A}
input:focus,select:focus{border-color:var(--purple);outline:none;box-shadow:0 0 0 3px var(--purple-soft)}
button,.btn{padding:11px 18px;border:0;border-radius:12px;background:var(--purple);color:#fff;font:inherit;font-weight:600;cursor:pointer}
button:hover,.btn:hover{filter:brightness(1.08);text-decoration:none}
button.ghost,.btn.ghost{background:var(--card);color:var(--ink);border:1px solid var(--line)}
.chips{display:flex;gap:8px;flex-wrap:wrap}.chip{padding:8px 14px;border-radius:999px;background:var(--card);border:1px solid var(--line);color:var(--mute);font-weight:500}
.chip.on{background:var(--purple);color:#fff;border-color:var(--purple)}.chip:hover{text-decoration:none;color:var(--ink)}
.pager{margin-top:14px;display:flex;gap:12px;align-items:center}
/* overview */
.dash{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:26px}
.stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:18px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:20px;padding:22px;color:var(--ink);display:block;transition:transform .15s}
.stat:hover{text-decoration:none;transform:translateY(-2px);border-color:#34344A}
.stat .ic{width:44px;height:44px;border-radius:12px;display:grid;place-items:center;margin-bottom:22px}
.stat .ic svg{width:24px;height:24px;stroke:currentColor;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
.stat .v{font-size:26px;font-weight:600;font-variant-numeric:tabular-nums;line-height:1.15}
.stat .l{color:var(--mute);font-size:13px;margin-top:6px}
.stat.g .ic{background:var(--green-soft);color:var(--green)}.stat.g .v{color:var(--green)}
.stat.p .ic{background:var(--purple-soft);color:#B7A6FF}
.stat.r .ic{background:var(--red-soft);color:var(--red)}.stat.r .v{color:var(--red)}
.stat.y .ic{background:var(--yellow-soft);color:var(--yellow)}.stat.y .v{color:var(--yellow)}
.chart{background:var(--card);border:1px solid var(--line);border-radius:20px;padding:22px 22px 12px}
.chart .top{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:8px}
.chart svg{width:100%;height:auto;display:block}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:13px;color:var(--mute)}.legend i{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:7px;vertical-align:0}
.rail h2{margin-top:6px}
.feed{list-style:none;margin:0 0 26px;padding:0}
.feed li{display:flex;gap:12px;align-items:flex-start;padding:10px 0}
.feed .ic{width:40px;height:40px;border-radius:12px;background:var(--card);border:1px solid var(--line);display:grid;place-items:center;flex:none}
.feed .ic svg{width:18px;height:18px;stroke:currentColor;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
.feed .t{font-weight:500;font-size:13.5px;line-height:1.3;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.feed .d{color:var(--mute);font-size:12px;margin-top:2px}
.classbar{display:flex;height:10px;border-radius:99px;overflow:hidden;background:#2A2A35;margin:12px 0 10px}.classbar span{display:block}
.grid2{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(0,1fr);gap:24px}
/* company title block */
.tb{display:grid;grid-template-columns:minmax(0,2.3fr) minmax(0,1.1fr) minmax(0,1.1fr) 170px;grid-template-areas:"name name name cls" "rev vat code cls" "city web web rel";
gap:14px;margin-bottom:26px}
.tb>div{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:16px 18px;min-width:0}
.tb .k{font-size:12px;color:var(--mute);margin-bottom:4px}.tb .v{font-weight:500;overflow-wrap:anywhere}
.tb .name{grid-area:name}.tb .name h1{font-size:30px}
.tb .cls-cell{grid-area:cls;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;background:linear-gradient(160deg,#2A2440,#17171F)}
.tb .cls-cell .letter{font-size:88px;line-height:.95;font-weight:700;color:#B7A6FF}
.tb .cls-cell.A{background:linear-gradient(160deg,#4A3A10,#1E1A10);border-color:#5A4614}.tb .cls-cell.A .letter{color:var(--yellow)}
.tb .cls-cell.none .letter{color:#4A4A58;font-size:56px}
.tb .rev{grid-area:rev}.tb .rev .v{font-size:24px;font-weight:600;color:var(--green);font-variant-numeric:tabular-nums}
.tb .vat{grid-area:vat}.tb .code{grid-area:code}.tb .city{grid-area:city}.tb .web{grid-area:web}.tb .rel{grid-area:rel}
.tb .note{grid-column:1/-1;font-size:12.5px;color:var(--mute)}
/* timeline */
.tl{list-style:none;margin:0;padding:6px 0}
.tl li{position:relative;padding:12px 18px 12px 42px;border-bottom:1px solid var(--line)}.tl li:last-child{border-bottom:0}
.tl li::before{content:"";position:absolute;left:18px;top:18px;width:10px;height:10px;border-radius:50%;background:var(--purple);box-shadow:0 0 0 4px var(--purple-soft)}
.tl li.calls::before{background:var(--green);box-shadow:0 0 0 4px var(--green-soft)}.tl li.emails::before{background:var(--blue);box-shadow:0 0 0 4px var(--blue-soft)}
.tl li.meetings::before{background:var(--yellow);box-shadow:0 0 0 4px var(--yellow-soft)}.tl li.tasks::before{background:var(--red);box-shadow:0 0 0 4px var(--red-soft)}
.tl .k{font-size:12px;color:var(--mute);margin-bottom:2px}.tl .t{white-space:pre-wrap}
/* board */
.board{display:flex;gap:14px;overflow-x:auto;padding-bottom:12px;align-items:flex-start}
.col{min-width:260px;flex:1;background:var(--side);border:1px solid var(--line);border-radius:18px;padding:12px}
.col h3{margin:4px 4px 12px;font-size:14px;font-weight:600;display:flex;justify-content:space-between;align-items:center;color:#fff}
.col h3 span.n{font-variant-numeric:tabular-nums;color:var(--c,#8C8C9C);background:#22222C;border-radius:99px;padding:1px 9px;font-size:12px}
.col h3::before{content:"";width:8px;height:8px;border-radius:50%;background:var(--c,#8C8C9C);margin-right:8px}
.col h3 span:first-child{flex:1}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px 13px;margin-bottom:10px}
.card .t{font-weight:500;line-height:1.35}.card .amt{font-weight:600;font-variant-numeric:tabular-nums;margin-top:6px;color:var(--c,#fff)}.card .m{color:var(--mute);font-size:12px;margin-top:4px;overflow-wrap:anywhere}
.more{font-size:12.5px;color:var(--mute);padding:4px}
/* chat */
#chat{height:58vh;overflow-y:auto;background:var(--card);border:1px solid var(--line);border-radius:20px;padding:20px}
.msg{margin:10px 0;max-width:78%;padding:11px 15px;border-radius:16px;white-space:pre-wrap;line-height:1.5}
.msg.u{background:var(--purple);color:#fff;margin-left:auto;border-bottom-right-radius:5px}.msg.a{background:var(--card2);border-bottom-left-radius:5px}
label.muted{color:var(--mute)}
/* AI dock */
.dock{position:fixed;left:calc(50% + 120px);bottom:20px;transform:translateX(-50%);width:min(760px,calc(100vw - 300px));z-index:30;display:flex;gap:8px;align-items:center;padding:8px 8px 8px 18px;
background:rgba(23,23,31,.95);border:1px solid #34344A;border-radius:16px;box-shadow:0 18px 50px rgba(0,0,0,.55),0 0 0 1px rgba(124,92,255,.15);backdrop-filter:blur(8px)}
.dock span{color:#B7A6FF;font-weight:600;white-space:nowrap;display:flex;gap:8px;align-items:center}
.dock span svg{width:18px;height:18px;stroke:currentColor;fill:none;stroke-width:1.8}
.dock input{flex:1;background:transparent;border:0;color:#fff;font-size:14.5px;padding:10px 6px}.dock input:focus{box-shadow:none}
.empty{padding:36px;text-align:center;color:var(--mute)}
.err{background:var(--red-soft);color:var(--red);border-radius:14px;padding:14px;white-space:pre-wrap;font-size:12.5px}
@media(max-width:1180px){.dash{grid-template-columns:1fr}.stats{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:900px){body{grid-template-columns:1fr}.side{position:static;height:auto;padding:14px 16px;gap:12px}.nav{flex-direction:row;flex-wrap:wrap}.nav a{padding:7px 10px}.nav a svg{display:none}.side .foot{display:none}
main{padding:20px 16px 120px}main table{display:block;overflow-x:auto}.grid2{grid-template-columns:1fr}h1{font-size:23px}
.tb{grid-template-columns:1fr 1fr;grid-template-areas:"name name" "cls rev" "vat code" "city web" "rel rel"}.tb .name h1{font-size:23px}.tb .rev .v{font-size:18px}.tb .cls-cell .letter{font-size:60px}
.dock{left:50%;width:calc(100vw - 32px)}.dock span{display:none}}
@media(prefers-reduced-motion:reduce){*{transition:none!important}}
"""

NAV = [("", "Overview"), ("companies", "Companies"), ("contacts", "Contacts"), ("deals", "Deals board"), ("tickets", "Tickets"),
       ("dormant", "Dormant customers"), ("products", "Price list"), ("assistant", "Assistant")]


ICONS = {
    "": '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
    "companies": '<path d="M3 21h18"/><path d="M5 21V7l7-4 7 4v14"/><path d="M9 21v-4h6v4"/><path d="M9 10h.01M15 10h.01M9 13.5h.01M15 13.5h.01"/>',
    "contacts": '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.8-3.6 3.4-5.5 6.5-5.5s5.7 1.9 6.5 5.5"/><path d="M16 4.5a3.3 3.3 0 0 1 0 6.5M18 14.6c2 .7 3.2 2.5 3.6 5.4"/>',
    "deals": '<rect x="3" y="4" width="5" height="16" rx="1.5"/><rect x="10" y="4" width="5" height="11" rx="1.5"/><rect x="17" y="4" width="4" height="7" rx="1.5"/>',
    "tickets": '<path d="M3 9V6a1 1 0 0 1 1-1h16a1 1 0 0 1 1 1v3a3 3 0 0 0 0 6v3a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-3a3 3 0 0 0 0-6Z"/><path d="M14 5v14"/>',
    "dormant": '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5Z"/>',
    "products": '<path d="M21 8 12 3 3 8v8l9 5 9-5Z"/><path d="M3 8l9 5 9-5M12 13v8"/>',
    "assistant": '<path d="M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8Z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8Z"/>',
}


def icon(k):
    return f'<svg viewBox="0 0 24 24" aria-hidden="true">{ICONS.get(k, "")}</svg>'


def page(title, body, on=""):
    nav = "".join(f'<a class="{"on" if k == on else ""}" href="/{k}">{icon(k)}<span>{l}</span></a>' for k, l in NAV)
    dock = "" if on == "assistant" else f'<form class="dock" action="/assistant" method="get"><span>{icon("assistant")}Ask the CRM</span><input name="q" placeholder="Es. Quali sono i miei clienti di classe A? Segna come vinta la trattativa di…" aria-label="Ask the assistant"><button>Ask</button></form>'
    return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)} · Brambilla CRM</title>{FONTS}<style>{CSS}</style></head><body>
<aside class="side"><a class="brand" href="/"><div class="mark">BF</div><b>Brambilla CRM<small>Forniture industriali</small></b></a><nav class="nav">{nav}</nav>
<div class="foot">Migrated from Sinergia 4</div></aside><main>{body}</main>{dock}</body></html>""")


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
FEED_ICON = {
    "notes": ('<path d="M6 3h9l4 4v14H6z"/><path d="M14 3v5h5M9 13h7M9 17h5"/>', "var(--purple)"),
    "calls": ('<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2"/>', "var(--green)"),
    "emails": ('<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/>', "var(--blue)"),
    "meetings": ('<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/>', "var(--yellow)"),
    "tasks": ('<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>', "var(--red)"),
}
ACT_TEXT = {"notes": ("hs_note_body",), "calls": ("hs_call_title", "hs_call_body"), "emails": ("hs_email_subject", "hs_email_text"), "meetings": ("hs_meeting_title", "hs_meeting_body")}
ACT_LABEL = {"notes": "Note", "calls": "Call", "emails": "Email", "meetings": "Meeting"}
_OV_CACHE = {}


def _fmt_dt(v):
    v = str(v or "")
    return f"{v[8:10]}/{v[5:7]}/{v[0:4]} {v[11:16]}".strip() if len(v) >= 10 else ""


def _smooth(pts, floor=1e9):
    d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
    for i in range(len(pts) - 1):
        p0 = pts[i - 1] if i else pts[i]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[i + 2] if i + 2 < len(pts) else p2
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, min(floor, p1[1] + (p2[1] - p0[1]) / 6))
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, min(floor, p2[1] - (p3[1] - p1[1]) / 6))
        d += f" C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}"
    return d


def area_chart(series):
    W, H, L, R, T, B = 760, 270, 52, 12, 14, 30
    mx = max([v for _, _, vals in series for v in vals] + [1])
    step = 10 ** (len(str(int(mx))) - 1)
    top = ((int(mx / step)) + 1) * step
    xs = [L + i * (W - L - R) / 11 for i in range(12)]
    y = lambda v: T + (H - T - B) * (1 - v / top)
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Won and lost deal value per month in 2025"><defs>']
    for i, (_, col, _) in enumerate(series):
        out.append(f'<linearGradient id="g{i}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{col}" stop-opacity=".38"/><stop offset="1" stop-color="{col}" stop-opacity="0"/></linearGradient>')
    out.append("</defs>")
    for k in range(5):
        v = top * k / 4
        yy = y(v)
        out.append(f'<line x1="{L}" x2="{W - R}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="#262631" stroke-dasharray="{"0" if k == 0 else "4 6"}"/>')
        lab = f"{v / 1e6:.0f}M" if top >= 4e6 else f"{v / 1e3:.0f}k"
        out.append(f'<text x="{L - 10}" y="{yy + 4:.1f}" text-anchor="end" fill="#8C8C9C" font-size="11">€{lab}</text>')
    for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]):
        out.append(f'<text x="{xs[i]:.1f}" y="{H - 8}" text-anchor="middle" fill="#8C8C9C" font-size="11">{m}</text>')
    for i, (name, col, vals) in enumerate(series):
        pts = [(xs[j], y(max(v, 0))) for j, v in enumerate(vals)]
        line = _smooth(pts, y(0))
        out.append(f'<path d="{line} L{xs[-1]:.1f},{y(0):.1f} L{xs[0]:.1f},{y(0):.1f} Z" fill="url(#g{i})"/>')
        out.append(f'<path d="{line}" fill="none" stroke="{col}" stroke-width="2.6" stroke-linecap="round"/>')
        for j, (px, py) in enumerate(pts):
            out.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3.2" fill="#17171F" stroke="{col}" stroke-width="2"><title>{name} · {["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][j]}: {money(vals[j])}</title></circle>')
    out.append("</svg>")
    return "".join(out)


def _overview_data(c):
    key = c.execute("SELECT count(*), max(id) FROM objects").fetchone()
    hit = _OV_CACHE.get("d")
    if hit and hit[0] == key and time.time() - hit[1] < 300:
        return hit[2]
    eur = "CAST(json_extract(props,'$.amount') AS REAL)*CASE json_extract(props,'$.deal_currency_code') WHEN 'USD' THEN 0.92 WHEN 'GBP' THEN 1.17 ELSE 1 END"
    won, lost = [0.0] * 12, [0.0] * 12
    for m, st, v in c.execute(f"""SELECT CAST(substr(json_extract(props,'$.closedate'),6,2) AS INTEGER), json_extract(props,'$.dealstage'), sum({eur})
        FROM objects WHERE type='deals' AND archived=0 AND json_extract(props,'$.closedate') LIKE '2025-%' AND json_extract(props,'$.dealstage') IN ('closedwon','closedlost') GROUP BY 1,2"""):
        if m and 1 <= m <= 12:
            (won if st == "closedwon" else lost)[m - 1] = v or 0.0
    now = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    acts = c.execute("""SELECT id, type, props FROM objects WHERE type IN ('notes','calls','emails','meetings') AND archived=0
        AND json_extract(props,'$.hs_timestamp') <= ? ORDER BY json_extract(props,'$.hs_timestamp') DESC LIMIT 6""", (now,)).fetchall()
    tasks = c.execute("""SELECT id, props FROM objects WHERE type='tasks' AND archived=0 AND coalesce(json_extract(props,'$.hs_task_status'),'')!='COMPLETED'
        ORDER BY json_extract(props,'$.hs_timestamp') LIMIT 6""").fetchall()
    tickets = c.execute("""SELECT id, props FROM objects WHERE type='tickets' AND archived=0 ORDER BY json_extract(props,'$.createdate') DESC LIMIT 4""").fetchall()
    d = (won, lost, acts, tasks, tickets)
    _OV_CACHE["d"] = (key, time.time(), d)
    return d


def _feed_item(kind, title, sub, href=None):
    ic, col = FEED_ICON.get(kind, FEED_ICON["notes"])
    t = html.escape(title or "—")
    if href:
        t = f'<a href="{href}" style="color:inherit">{t}</a>'
    return f'<li><div class="ic" style="color:{col}"><svg viewBox="0 0 24 24">{ic}</svg></div><div style="min-width:0"><div class="t">{t}</div><div class="d">{html.escape(sub)}</div></div></li>'


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
        won, lost, acts, tasks, tickets = _overview_data(c)
        total_cls = sum(cls.values()) or 1
        pal = (("A", "var(--yellow)"), ("B", "var(--purple)"), ("C", "#4A4A58"))
        bar = "".join(f'<span style="width:{cls.get(k, 0) / total_cls * 100:.2f}%;background:{col}"></span>' for k, col in pal)
        legend = "".join(f'<span><i style="background:{col}"></i>Class {k} · {cls.get(k, 0)}</span>' for k, col in pal)
        _, top, _ = _search("companies", None, [{"propertyName": "classe_cliente", "operator": "HAS_PROPERTY"}], 8, 0, [{"propertyName": "fatturato_2025", "direction": "DESCENDING"}])
        rows = "".join(f'<tr><td class="name"><a href="/companies/{o["id"]}">{e(o["props"].get("name"))}</a><div class="muted small">{e(o["props"].get("city"))}</div></td><td>{clsbadge(o["props"].get("classe_cliente"))}</td><td class="num">{money(o["props"].get("fatturato_2025"))}</td></tr>' for o in top)
        fmt = lambda x: f"{x:,}".replace(",", ".")
        n = lambda k: fmt(counts.get(k, 0))
        acts_n = sum(counts.get(k, 0) for k in ("notes", "calls", "emails", "meetings"))
        st = lambda cls_, ic, v, l, href: f'<a class="stat {cls_}" href="{href}"><div class="ic"><svg viewBox="0 0 24 24">{ic}</svg></div><div class="v">{v}</div><div class="l">{l}</div></a>'
        coin = '<circle cx="12" cy="12" r="9"/><path d="M15 8.5c-.7-.9-1.8-1.5-3-1.5-2 0-3.5 1.6-3.5 5s1.5 5 3.5 5c1.2 0 2.3-.6 3-1.5M7 11h6M7 13.5h6"/>'
        stats = (st("g", coin, money_short(rev_total), "Revenue won in 2025", "/companies?sort=rev")
                 + st("p", ICONS["companies"], n("companies"), "Companies", "/companies")
                 + st("y", ICONS["deals"], fmt(open_deals), "Open sales deals", "/deals")
                 + st("r", ICONS["tickets"], fmt(open_tk), "Open support tickets", "/tickets"))
        chart = area_chart([("Won", "#34D399", won), ("Lost", "#7C5CFF", lost)])
        feed = "".join(_feed_item(t, next((json.loads(pj).get(k) for k in ACT_TEXT[t] if json.loads(pj).get(k)), ""), f'{ACT_LABEL[t]} · {_fmt_dt(json.loads(pj).get("hs_timestamp"))}') for _, t, pj in acts) or '<li class="muted">No activity yet.</li>'
        up = "".join(_feed_item("tasks", json.loads(pj).get("hs_task_subject"), f'Due {_fmt_dt(json.loads(pj).get("hs_timestamp"))[:10]}') for _, pj in tasks)
        up += "".join(_feed_item("meetings", json.loads(pj).get("subject"), f'New ticket · {_fmt_dt(json.loads(pj).get("createdate"))[:10]}', f"/tickets?q={quote(str(json.loads(pj).get('subject') or ''))}") for _, pj in tickets[: max(0, 6 - len(tasks))])
        body = f"""<div class="head"><div><h1>Dashboard</h1><div class="sub">Brambilla Forniture after the move from Sinergia 4 · ask the assistant at the bottom of any page</div></div>
<form class="bar" style="margin:0" action="/companies"><input name="q" placeholder="Search a company…" style="width:260px"><button>Search</button></form></div>
<div class="dash"><div style="min-width:0">
<div class="stats">{stats}</div>
<section class="blk"><div class="chart"><div class="top"><h2 style="margin:0">Closed deals, 2025</h2><div class="legend"><span><i style="background:#34D399"></i>Won {money_short(sum(won))}</span><span><i style="background:#7C5CFF"></i>Lost {money_short(sum(lost))}</span><span class="chip" style="padding:5px 12px">By month</span></div></div>{chart}</div></section>
<section class="blk"><div class="grid2"><div><h2>Top customers by 2025 revenue</h2><table><thead><tr><th>Company</th><th>Class</th><th class="num">2025 revenue</th></tr></thead><tbody>{rows}</tbody></table></div>
<div><h2>Customer classes</h2><div class="panel pad"><div class="muted small">{fmt(total_cls)} companies with revenue in 2025 · A from € 100.000, B from € 20.000</div><div class="classbar">{bar}</div><div class="legend">{legend}</div></div>
<h2 style="margin-top:22px">Records in the CRM</h2><div class="panel pad"><table style="border:0;background:transparent"><tbody>
<tr><td>Contacts</td><td class="num">{n('contacts')}</td></tr><tr><td>Deals</td><td class="num">{n('deals')}</td></tr>
<tr><td>Quote lines</td><td class="num">{n('line_items')}</td></tr><tr><td>Products</td><td class="num">{n('products')}</td></tr>
<tr><td>Tickets</td><td class="num">{n('tickets')}</td></tr><tr><td>Activities</td><td class="num">{fmt(acts_n)}</td></tr>
<tr><td><a href="/dormant">Dormant customers</a></td><td class="num">{fmt(dormant)}</td></tr></tbody></table></div></div></div></section>
</div>
<aside class="rail"><h2>Latest activity</h2><ul class="feed">{feed}</ul><h2>Upcoming</h2><ul class="feed">{up or '<li class="muted">Nothing scheduled.</li>'}</ul></aside></div>"""
        return page("Dashboard", body, "")
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

"""Minimal server-rendered UI (English)."""
import html
import json
from urllib.parse import urlencode

from starlette.responses import HTMLResponse, RedirectResponse
from starlette.routing import Route
from starlette.concurrency import run_in_threadpool

from . import store, schema

CSS = """
:root{--bg:#f6f5f2;--card:#fff;--ink:#1d1f23;--mute:#6b7078;--line:#e4e2dc;--acc:#1f5f5b;--acc2:#e8f1ef;--warn:#9a3b1b;--a:#1f5f5b;--b:#8a6d1f;--c:#6b7078}
*{box-sizing:border-box}body{margin:0;font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif;background:var(--bg);color:var(--ink)}
a{color:var(--acc);text-decoration:none}a:hover{text-decoration:underline}
header{display:flex;align-items:center;gap:22px;padding:12px 24px;background:#16302e;color:#fff;position:sticky;top:0;z-index:5;flex-wrap:wrap}
header b{font-size:15px;letter-spacing:.3px}header nav a{color:#cfe3df;margin-right:14px}header nav a.on{color:#fff;font-weight:600}
main{padding:22px 24px;max-width:1400px;margin:0 auto}h1{font-size:22px;margin:0 0 14px}h2{font-size:15px;margin:22px 0 8px;color:var(--mute);text-transform:uppercase;letter-spacing:.6px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}th{background:#faf9f6;font-weight:600;color:var(--mute);font-size:12px;text-transform:uppercase;letter-spacing:.4px}
tr:last-child td{border-bottom:0}.num{text-align:right;font-variant-numeric:tabular-nums}
.pill{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;background:var(--acc2);color:var(--acc);font-weight:600}
.cls{display:inline-block;width:26px;height:26px;border-radius:6px;text-align:center;line-height:26px;font-weight:700;color:#fff}
.cls.A{background:var(--a)}.cls.B{background:var(--b)}.cls.C{background:var(--c)}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-bottom:8px}.kpi .v{font-size:22px;font-weight:700}.kpi .l{color:var(--mute);font-size:12px}
form.s{display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap}input,select{padding:7px 10px;border:1px solid var(--line);border-radius:8px;font:inherit;background:#fff}button{padding:7px 14px;border:0;border-radius:8px;background:var(--acc);color:#fff;font:inherit;cursor:pointer}
.board{display:flex;gap:12px;overflow-x:auto;padding-bottom:10px}.col{min-width:250px;flex:1;background:#eceae4;border-radius:10px;padding:10px}
.col h3{margin:0 0 8px;font-size:13px;display:flex;justify-content:space-between}.deal{background:#fff;border:1px solid var(--line);border-radius:8px;padding:8px 10px;margin-bottom:8px}
.deal .t{font-weight:600}.deal .m{color:var(--mute);font-size:12px}.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}@media(max-width:900px){.grid2{grid-template-columns:1fr}}
.tl{border-left:2px solid var(--line);margin-left:6px;padding-left:14px}.tl .it{margin-bottom:10px}.tl .k{font-size:11px;text-transform:uppercase;color:var(--mute);letter-spacing:.5px}
.pager{margin-top:10px;display:flex;gap:10px}.muted{color:var(--mute)}
#chat{height:58vh;overflow-y:auto;background:#fff;border:1px solid var(--line);border-radius:10px;padding:14px}.msg{margin:8px 0;max-width:80%;padding:9px 12px;border-radius:10px;white-space:pre-wrap}
.msg.u{background:var(--acc);color:#fff;margin-left:auto}.msg.a{background:#f0efe9}
"""

NAV = [("companies", "Companies"), ("contacts", "Contacts"), ("deals", "Deals board"), ("tickets", "Tickets"), ("dormant", "Dormant customers"), ("products", "Products"), ("assistant", "Assistant")]


def page(title, body, on=""):
    nav = "".join(f'<a class="{"on" if k == on else ""}" href="/{k}">{l}</a>' for k, l in NAV)
    return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)} · Brambilla CRM</title><style>{CSS}</style></head><body><header><b>Brambilla CRM</b><nav>{nav}</nav></header><main>{body}</main></body></html>""")


e = lambda v: html.escape(str(v)) if v not in (None, "") else '<span class="muted">—</span>'


def money(v, cur="EUR"):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return '<span class="muted">—</span>'
    s = f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    sym = {"EUR": "€", "USD": "$", "GBP": "£"}.get(cur or "EUR", cur or "")
    return f"{sym} {s}"


def stage_labels():
    m = {}
    for t in ("deals", "tickets"):
        for p in store.pipelines(t):
            for s in p["stages"]:
                m[(p["id"], s["id"])] = s["label"]
    return m


def pager(req, total, after, nxt):
    q = dict(req.query_params)
    out = f'<div class="pager"><span class="muted">{total} records</span>'
    if nxt:
        q["after"] = nxt
        out += f'<a href="?{urlencode(q)}">Next →</a>'
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


async def companies(req):
    def work():
        q = req.query_params.get("q", "")
        cls = req.query_params.get("class", "")
        after = int(req.query_params.get("after") or 0)
        f = [{"propertyName": "classe_cliente", "operator": "EQ", "value": cls}] if cls else None
        sorts = [{"propertyName": "fatturato_2025", "direction": "DESCENDING"}] if cls or req.query_params.get("sort") == "rev" else None
        total, objs, nxt = _search("companies", q, f, 50, after, sorts)
        rows = "".join(f"""<tr><td><a href="/companies/{o['id']}">{e(o['props'].get('name'))}</a></td><td>{e(o['props'].get('domain'))}</td><td>{e(o['props'].get('city'))} {e(o['props'].get('state'))}</td>
<td>{e(o['props'].get('partita_iva'))}</td><td class="num">{money(o['props'].get('fatturato_2025'))}</td><td>{('<span class="cls ' + o['props']['classe_cliente'] + '">' + o['props']['classe_cliente'] + '</span>') if o['props'].get('classe_cliente') else ''}</td></tr>""" for o in objs)
        sel = "".join(f'<option {"selected" if cls == c else ""} value="{c}">{c or "All classes"}</option>' for c in ("", "A", "B", "C"))
        return page("Companies", f"""<h1>Companies</h1><form class="s"><input name="q" placeholder="Search name, domain…" value="{html.escape(q)}"><select name="class">{sel}</select><button>Search</button><a href="?sort=rev" style="align-self:center">Top 2025 revenue</a></form>
<table><tr><th>Name</th><th>Domain</th><th>City</th><th>VAT</th><th class="num">2025 revenue</th><th>Class</th></tr>{rows}</table>{pager(req, total, after, nxt)}""", "companies")
    return await run_in_threadpool(work)


def _assoc_objs(oid, t, limit=200):
    out = []
    for i, _ in store.get_assocs(oid, t)[:limit]:
        o = store.get_obj(t, i)
        if o:
            out.append(o)
    return out


async def company(req):
    def work():
        c = store.get_obj("companies", req.path_params["id"])
        if not c:
            return page("Not found", "<h1>Company not found</h1>")
        p = c["props"]
        sl = stage_labels()
        contacts = _assoc_objs(c["id"], "contacts")
        deals = _assoc_objs(c["id"], "deals")
        deals.sort(key=lambda d: d["props"].get("closedate") or "", reverse=True)
        tickets = _assoc_objs(c["id"], "tickets")
        acts = []
        seen = set()
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
        kp = f"""<div class="kpis"><div class="card kpi"><div class="l">2025 revenue</div><div class="v">{money(p.get('fatturato_2025'))}</div></div>
<div class="card kpi"><div class="l">Customer class</div><div class="v">{('<span class="cls ' + cls + '">' + cls + '</span>') if cls else '<span class="muted">—</span>'}</div></div>
<div class="card kpi"><div class="l">Contacts / Deals / Tickets</div><div class="v">{len(contacts)} / {len(deals)} / {len(tickets)}</div></div>
<div class="card kpi"><div class="l">VAT number</div><div class="v" style="font-size:16px">{e(p.get('partita_iva'))}</div></div></div>"""
        info = f"""<div class="card"><b>Domain</b> {e(p.get('domain'))} {('· also ' + html.escape(p['hs_additional_domains'].replace(';', ', '))) if p.get('hs_additional_domains') else ''}<br><b>City</b> {e(p.get('city'))} ({e(p.get('state'))})<br><b>Legacy ID</b> {e(p.get('id_legacy'))}<br><span class="muted">{e(p.get('description'))}</span></div>"""
        crow = "".join(f"<tr><td>{e(o['props'].get('firstname'))} {e(o['props'].get('lastname'))}</td><td>{e(o['props'].get('email'))}</td><td>{e(o['props'].get('phone'))}</td><td><span class='pill'>{e(o['props'].get('lifecyclestage'))}</span></td></tr>" for o in contacts)
        drow = "".join(f"<tr><td>{e(o['props'].get('dealname'))}</td><td>{e(sl.get((o['props'].get('pipeline'), o['props'].get('dealstage'))))}</td><td class='num'>{money(o['props'].get('amount'), o['props'].get('deal_currency_code'))}</td><td>{e((o['props'].get('closedate') or '')[:10])}</td><td>{e(o['props'].get('commerciale'))}</td></tr>" for o in deals)
        trow = "".join(f"<tr><td>{e(o['props'].get('subject'))}</td><td>{e(sl.get((o['props'].get('hs_pipeline'), o['props'].get('hs_pipeline_stage'))))}</td><td>{e(o['props'].get('hs_ticket_priority'))}</td><td>{e((o['props'].get('createdate') or '')[:10])}</td></tr>" for o in tickets)
        body_k = {"notes": "hs_note_body", "calls": "hs_call_body", "emails": "hs_email_text", "meetings": "hs_meeting_body", "tasks": "hs_task_subject"}
        tl = "".join(f"<div class='it'><div class='k'>{at[:-1]} · {e((o['props'].get('hs_timestamp') or '')[:16].replace('T', ' '))} · {e(o['props'].get('autore'))}</div>{e(o['props'].get(body_k[at]))}</div>" for at, o in acts[:60])
        return page(p.get("name") or "Company", f"""<h1>{e(p.get('name'))}</h1>{kp}<div class="grid2"><div>{info}<h2>Contacts</h2><table><tr><th>Name</th><th>Email</th><th>Phone</th><th>Stage</th></tr>{crow}</table>
<h2>Deals</h2><table><tr><th>Deal</th><th>Stage</th><th class="num">Amount</th><th>Close</th><th>Sales rep</th></tr>{drow}</table><h2>Tickets</h2><table><tr><th>Subject</th><th>Status</th><th>Priority</th><th>Opened</th></tr>{trow}</table></div>
<div><h2>History</h2><div class="card tl">{tl or '<span class="muted">No activity</span>'}</div></div></div>""", "companies")
    return await run_in_threadpool(work)


async def contacts(req):
    def work():
        q = req.query_params.get("q", "")
        after = int(req.query_params.get("after") or 0)
        total, objs, nxt = _search("contacts", q, None, 50, after)
        rows = "".join(f"<tr><td>{e(o['props'].get('firstname'))} {e(o['props'].get('lastname'))}</td><td>{e(o['props'].get('email'))}</td><td>{e(o['props'].get('phone'))}</td><td><span class='pill'>{e(o['props'].get('lifecyclestage'))}</span></td><td>{('<a href=/companies/' + o['props']['associatedcompanyid'] + '>company</a>') if o['props'].get('associatedcompanyid') else ''}</td></tr>" for o in objs)
        return page("Contacts", f"""<h1>Contacts</h1><form class="s"><input name="q" placeholder="Search name, email…" value="{html.escape(q)}"><button>Search</button></form>
<table><tr><th>Name</th><th>Email</th><th>Phone</th><th>Lifecycle</th><th></th></tr>{rows}</table>{pager(req, total, after, nxt)}""", "contacts")
    return await run_in_threadpool(work)


async def deals(req):
    def work():
        pls = store.pipelines("deals")
        pid = req.query_params.get("pipeline") or "default"
        q = req.query_params.get("q", "")
        owner = req.query_params.get("owner", "")
        pl = store.pipeline_get("deals", pid) or pls[0]
        cols = ""
        for s in pl["stages"]:
            f = [{"propertyName": "pipeline", "operator": "EQ", "value": pl["id"]}, {"propertyName": "dealstage", "operator": "EQ", "value": s["id"]}]
            if owner:
                f.append({"propertyName": "commerciale", "operator": "EQ", "value": owner})
            total, objs, _ = _search("deals", q, f, 30, 0, [{"propertyName": "closedate", "direction": "DESCENDING"}])
            cards = "".join(f"<div class='deal'><div class='t'>{e(o['props'].get('dealname'))}</div><div class='m'>{money(o['props'].get('amount'), o['props'].get('deal_currency_code'))} · {e((o['props'].get('closedate') or '')[:10])}<br>{e(o['props'].get('commerciale'))}</div></div>" for o in objs)
            cols += f"<div class='col'><h3><span>{e(s['label'])}</span><span class='muted'>{total}</span></h3>{cards}</div>"
        sel = "".join(f'<option value="{p["id"]}" {"selected" if p["id"] == pl["id"] else ""}>{html.escape(p["label"])}</option>' for p in pls)
        return page("Deals", f"""<h1>Deals board</h1><form class="s"><select name="pipeline">{sel}</select><input name="q" placeholder="Search deal…" value="{html.escape(q)}"><input name="owner" placeholder="Sales rep email" value="{html.escape(owner)}"><button>Filter</button></form><div class="board">{cols}</div>""", "deals")
    return await run_in_threadpool(work)


async def tickets(req):
    def work():
        q = req.query_params.get("q", "")
        stage = req.query_params.get("stage", "")
        after = int(req.query_params.get("after") or 0)
        sl = stage_labels()
        pl = store.pipeline_by_label("tickets", "Assistenza") or store.pipelines("tickets")[0]
        f = [{"propertyName": "hs_pipeline_stage", "operator": "EQ", "value": stage}] if stage else None
        total, objs, nxt = _search("tickets", q, f, 50, after, [{"propertyName": "createdate", "direction": "DESCENDING"}])
        rows = "".join(f"<tr><td>{e(o['props'].get('subject'))}</td><td><span class='pill'>{e(sl.get((o['props'].get('hs_pipeline'), o['props'].get('hs_pipeline_stage'))))}</span></td><td>{e(o['props'].get('hs_ticket_priority'))}</td><td>{e(o['props'].get('assegnatario'))}</td><td>{e((o['props'].get('createdate') or '')[:10])}</td><td>{e((o['props'].get('closed_date') or '')[:10])}</td></tr>" for o in objs)
        sel = '<option value="">All statuses</option>' + "".join(f'<option value="{s["id"]}" {"selected" if s["id"] == stage else ""}>{html.escape(s["label"])}</option>' for s in pl["stages"])
        return page("Tickets", f"""<h1>Support tickets</h1><form class="s"><input name="q" placeholder="Search subject…" value="{html.escape(q)}"><select name="stage">{sel}</select><button>Filter</button></form>
<table><tr><th>Subject</th><th>Status</th><th>Priority</th><th>Assignee</th><th>Opened</th><th>Closed</th></tr>{rows}</table>{pager(req, total, after, nxt)}""", "tickets")
    return await run_in_threadpool(work)


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
                rows += f"<tr><td><a href='/companies/{o['id']}'>{e(o['props'].get('name'))}</a></td><td>{e(o['props'].get('city'))}</td><td>{e(o['props'].get('domain'))}</td></tr>"
        return page("Dormant customers", f"""<h1>Dormant customers <span class="muted" style="font-size:14px">{len(ids)} companies with won deals and no activity in 2025</span></h1>
<table><tr><th>Company</th><th>City</th><th>Domain</th></tr>{rows}</table>""", "dormant")
    return await run_in_threadpool(work)


async def products(req):
    def work():
        q = req.query_params.get("q", "")
        after = int(req.query_params.get("after") or 0)
        total, objs, nxt = _search("products", q, None, 50, after)
        rows = "".join(f"<tr><td>{e(o['props'].get('hs_sku'))}</td><td>{e(o['props'].get('name'))}</td><td class='num'>{money(o['props'].get('price'))}</td></tr>" for o in objs)
        return page("Products", f"""<h1>Price list</h1><form class="s"><input name="q" placeholder="Search SKU or description…" value="{html.escape(q)}"><button>Search</button></form>
<table><tr><th>SKU</th><th>Description</th><th class="num">Price</th></tr>{rows}</table>{pager(req, total, after, nxt)}""", "products")
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


async def assistant(req):
    def users():
        out = []
        for (js,) in store.rconn().execute("SELECT json FROM owners ORDER BY id"):
            o = json.loads(js)
            if not o.get("archived"):
                out.append(o)
        return out
    us = await run_in_threadpool(users)
    opts = "".join(f'<option value="{html.escape(o["email"])}">{html.escape(o["firstName"] + " " + o["lastName"])} · {html.escape(o["email"])}</option>' for o in us)
    if not opts:
        opts = '<option value="">(no users yet: run the migration first)</option>'
    return page("Assistant", f"""<h1>Assistant</h1><p class="muted">Ask in Italian, as a Brambilla sales rep would. The assistant reads and updates the CRM.</p>
<div style="display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap;align-items:center"><span class="muted">Writing as</span><select id="user" style="min-width:320px">{opts}</select></div>
<div id="chat"></div><form id="f" class="s" style="margin-top:10px"><input id="m" style="flex:1;min-width:260px" placeholder="e.g. Quanto abbiamo fatturato con Officine Farina nel 2025?"><button>Send</button></form>
<script>
const msgs=[];const chat=document.getElementById('chat');
try{{const u=localStorage.getItem('user');if(u)user.value=u}}catch(e){{}}
function add(r,t){{const d=document.createElement('div');d.className='msg '+(r=='user'?'u':'a');d.textContent=t;chat.appendChild(d);chat.scrollTop=1e9}}
f.onsubmit=async ev=>{{ev.preventDefault();const t=m.value.trim();if(!t)return;m.value='';try{{localStorage.setItem('user',user.value)}}catch(e){{}}
msgs.push({{role:'user',content:t}});add('user',t);add('assistant','…');
const r=await fetch('/ui/agent',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{context:{{now:new Date().toISOString(),user:user.value}},messages:msgs}})}});
const j=await r.json().catch(()=>({{reply:'Error '+r.status}}));chat.lastChild.remove();const rep=j.reply||('Error '+r.status);msgs.push({{role:'assistant',content:rep}});add('assistant',rep)}}
</script>""", "assistant")


async def home(req):
    return RedirectResponse("/companies")


def routes():
    return [Route("/", home), Route("/companies", companies), Route("/companies/{id}", company), Route("/contacts", contacts),
            Route("/deals", deals), Route("/tickets", tickets), Route("/dormant", dormant), Route("/products", products),
            Route("/assistant", assistant), Route("/ui/agent", ui_agent, methods=["POST"])]

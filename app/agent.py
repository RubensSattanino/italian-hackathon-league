"""R13: chat assistant on OpenRouter (openai/gpt-6-luna) with tool calling over the CRM store."""
import csv
import io
import json
import os
import re
import time
import urllib.request
from datetime import datetime, timezone, timedelta

from . import store, schema
from .store import ApiError

MODEL = os.environ.get("AGENT_MODEL", "openai/gpt-6-luna")
API_URL = "https://openrouter.ai/api/v1/chat/completions"
FX = {"EUR": 1.0, "USD": 0.92, "GBP": 1.17}
BUDGET_S = 52

SYSTEM = """Sei l'assistente del CRM di Brambilla Forniture S.p.A. (distributore di forniture industriali). Parli con i commerciali in italiano, come un collega attento e conciso.

Contesto: oggi è {now} (usa SEMPRE questa data per "oggi", "tra sei mesi", "questo mese", ecc.). Chi ti scrive: {user} ({user_name}). "I miei clienti" = le aziende di cui {user} segue trattative (proprietà deals.commerciale) o ticket (tickets.assegnatario).

Come lavori:
- Usa gli strumenti per leggere e modificare il CRM. Non inventare MAI dati: ogni numero, nome, email che citi deve venire dagli strumenti.
- Prima di modificare, trova il record giusto (cerca per nome con `query`, poi verifica). Per "la trattativa di <azienda>": trova l'azienda, poi le sue trattative (get_associated) e considera quelle ancora aperte; se ce n'è una sola aperta è quella. Se ci sono più candidati plausibili e la richiesta non permette di scegliere, chiedi quale (elencandoli brevemente con i dati che li distinguono) e NON modificare nulla. Non fare domande inutili: se la richiesta è chiara, esegui.
- Se un'azienda/contatto/trattativa citata non esiste nel CRM, dillo chiaramente invece di crearla o indovinare (crea solo se ti viene chiesto di creare).
- Modifica SOLO i record e i campi che la richiesta chiede. Non toccare altro. Non creare duplicati: cerca prima se il record esiste già.
- Dopo una modifica, conferma in una frase cosa hai fatto (con i valori). Quello che dici di aver fatto deve essere vero.
- Se la richiesta va contro le regole o non si può fare, non farla e spiega perché in una frase. Regole: la partita IVA (companies.partita_iva, 11 cifre senza IT) è unica: non creare/assegnare una P.IVA già presente su un'altra azienda. Trattative e ticket possono essere assegnati solo a utenti ATTIVI (vedi list_users). Le email devono essere valide.
- Automazioni del CRM (non farle a mano, avvengono da sole): trattativa in Vinta (pipeline vendite) => ticket "Avvio fornitura - <titolo>"; trattativa in Persa => task "Richiamare: <titolo>" a 180 giorni; contatto senza azienda => associato all'azienda dal dominio email.
- Quando segni una trattativa come vinta o persa, imposta anche closedate a oggi se la richiesta non indica un'altra data.
- Pipeline trattative: Vendite = "default" (fasi: appointmentscheduled=Contatto, qualifiedtobuy=Qualifica, presentationscheduled=Presentazione, decisionmakerboughtin=Decisione, contractsent=Contratto, closedwon=Vinta, closedlost=Persa); Rinnovi (fasi Da rinnovare, In trattativa, Rinnovato, Non rinnovato: usa list_pipelines per gli id). Ticket: pipeline Assistenza (Aperto, In lavorazione, In attesa del cliente, Chiuso); priorità LOW/MEDIUM/HIGH/URGENT.
- Proprietà utili: companies(name, domain, city, state, partita_iva, fatturato_2025, classe_cliente A/B/C), contacts(firstname, lastname, email, phone, lifecyclestage: lead/opportunity/customer/other), deals(dealname, amount, deal_currency_code, pipeline, dealstage, closedate, commerciale), tickets(subject, content, hs_pipeline, hs_pipeline_stage, hs_ticket_priority, assegnatario), tasks(hs_task_subject, hs_task_body, hs_timestamp=scadenza, hs_task_status NOT_STARTED/COMPLETED, hs_task_priority), notes(hs_note_body, hs_timestamp), calls(hs_call_body, hs_timestamp), meetings(hs_meeting_title, hs_meeting_body, hs_timestamp), products(name, hs_sku BF-00000, price), line_items(name, quantity, price, hs_discount_percentage, hs_product_id).
- Fatturato: fatturato_2025 dell'azienda è già calcolato (trattative vinte 2025 meno storni, in EUR). Per altri anni o dettagli usa lo strumento revenue.
- Per attività (note, chiamate, task, riunioni) registrate da chi scrive: imposta hs_timestamp (ora se non indicato), autore={user} sulle note/chiamate/email/riunioni, hubspot_owner_id dell'utente se lo conosci, e associale al contatto/azienda/trattativa giusti.
- Allegati CSV: leggili con read_attachment; per aggiornare il listino usa apply_price_list.
- Rispondi in italiano, breve e chiaro. Numeri in formato italiano (es. 12.345,67 €)."""


# ------------------------------------------------------------------ tools
def _props_brief(o, props=None):
    p = o["props"]
    keep = props or list(p.keys())
    out = {"id": str(o["id"])}
    for k in keep:
        if k in ("hs_lastmodifieddate", "lastmodifieddate", "hs_object_id") and not props:
            continue
        v = p.get(k)
        if v is not None:
            out[k] = v if len(str(v)) < 400 else str(v)[:400] + "…"
    return out


DEFAULT_PROPS = {
    "companies": ["name", "domain", "city", "state", "partita_iva", "fatturato_2025", "classe_cliente", "hs_additional_domains"],
    "contacts": ["firstname", "lastname", "email", "phone", "lifecyclestage", "associatedcompanyid"],
    "deals": ["dealname", "amount", "deal_currency_code", "pipeline", "dealstage", "closedate", "commerciale"],
    "tickets": ["subject", "hs_pipeline_stage", "hs_ticket_priority", "assegnatario", "createdate", "closed_date"],
    "tasks": ["hs_task_subject", "hs_timestamp", "hs_task_status", "hubspot_owner_id"],
    "products": ["name", "hs_sku", "price"],
    "line_items": ["name", "quantity", "price", "hs_discount_percentage", "amount", "hs_product_id"],
    "notes": ["hs_note_body", "hs_timestamp", "autore"], "calls": ["hs_call_body", "hs_timestamp", "autore"],
    "emails": ["hs_email_text", "hs_timestamp", "autore"], "meetings": ["hs_meeting_title", "hs_meeting_body", "hs_timestamp", "autore"],
}


def t_search(a, ctx):
    t = schema.norm_type(a.get("object_type"))
    if not t:
        return {"error": "object_type non valido"}
    filters = []
    for f in a.get("filters") or []:
        ff = {"propertyName": f.get("property") or f.get("propertyName"), "operator": (f.get("operator") or "EQ").upper()}
        if "value" in f:
            ff["value"] = f["value"]
        if "values" in f:
            ff["values"] = f["values"]
        if "highValue" in f:
            ff["highValue"] = f["highValue"]
        filters.append(ff)
    body = {"limit": min(int(a.get("limit") or 20), 100)}
    if filters:
        body["filterGroups"] = [{"filters": filters}]
    if a.get("query"):
        body["query"] = a["query"]
    if a.get("sort_property"):
        body["sorts"] = [{"propertyName": a["sort_property"], "direction": "DESCENDING" if a.get("sort_desc") else "ASCENDING"}]
    total, objs, _ = store.search(t, body)
    if total == 0 and a.get("query") and len(str(a["query"]).split()) > 1:
        # relax: try dropping legal suffixes / words
        q = re.sub(r"\b(s\.?p\.?a\.?|s\.?r\.?l\.?s?|s\.?n\.?c\.?|s\.?a\.?s\.?)\b", "", a["query"], flags=re.I).strip()
        body["query"] = q
        total, objs, _ = store.search(t, body)
    props = a.get("properties") or DEFAULT_PROPS.get(t)
    return {"total": total, "results": [_props_brief(o, props) for o in objs]}


def t_get(a, ctx):
    t = schema.norm_type(a.get("object_type"))
    o = store.get_obj(t, a.get("id")) if t else None
    if not o:
        return {"error": "record non trovato"}
    res = _props_brief(o)
    for at in ("companies", "contacts", "deals", "tickets", "line_items"):
        if at == t:
            continue
        lst = store.get_assocs(o["id"], at)
        if lst:
            res["assoc_" + at] = [str(i) for i, _ in lst[:50]] + (["…(+%d)" % (len(lst) - 50)] if len(lst) > 50 else [])
    return res


def t_assoc(a, ctx):
    t = schema.norm_type(a.get("object_type"))
    to = schema.norm_type(a.get("to_type"))
    lst = store.get_assocs(a.get("id"), to)
    out = []
    for i, _ in lst[: int(a.get("limit") or 50)]:
        o = store.get_obj(to, i)
        if o:
            out.append(_props_brief(o, DEFAULT_PROPS.get(to)))
    return {"total": len(lst), "results": out}


def _assoc_specs(t, assocs):
    specs = []
    for x in assocs or []:
        tt = schema.norm_type(x.get("to_type"))
        if not tt:
            continue
        tid = schema.default_assoc_type(t, tt)
        specs.append({"to": {"id": x.get("to_id")}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": tid}]})
        if (t, tt) in (("contacts", "companies"), ("deals", "companies"), ("tickets", "companies")):
            specs.append({"to": {"id": x.get("to_id")}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": schema.ASSOC[(t, tt)][1][0]}]})
    return specs


def _check_user_fields(t, props):
    for k in ("commerciale", "assegnatario"):
        if props.get(k):
            u = _user(props[k])
            if not u:
                return f"{props[k]} non è un utente del CRM"
            if u.get("archived"):
                return f"{props[k]} non è più attivo in azienda: non può seguire trattative o ticket"
            props[k] = u["email"]
            props.setdefault("hubspot_owner_id", str(u["id"]))
    return None


def t_create(a, ctx):
    t = schema.norm_type(a.get("object_type"))
    props = dict(a.get("properties") or {})
    e = _check_user_fields(t, props)
    if e:
        return {"error": e}
    if t in ("notes", "calls", "emails", "meetings", "tasks") and not props.get("hs_timestamp"):
        props["hs_timestamp"] = ctx["now_iso"]
    if t in ("notes", "calls", "emails", "meetings") and not props.get("autore"):
        props["autore"] = ctx["user"]
    if t in ("notes", "calls", "emails", "meetings", "tasks") and not props.get("hubspot_owner_id") and ctx.get("owner_id"):
        props["hubspot_owner_id"] = ctx["owner_id"]
    if t == "tasks":
        props.setdefault("hs_task_status", "NOT_STARTED")
    if t == "meetings" and props.get("hs_timestamp"):
        props.setdefault("hs_meeting_start_time", props["hs_timestamp"])
    try:
        o = store.create(t, props, _assoc_specs(t, a.get("associations")), ctx={"now": ctx["now_iso"]})
    except ApiError as e:
        return {"error": e.message, "status": e.status}
    ctx["writes"] += 1
    return {"ok": True, "created": _props_brief(o)}


def t_update(a, ctx):
    t = schema.norm_type(a.get("object_type"))
    props = dict(a.get("properties") or {})
    e = _check_user_fields(t, props)
    if e:
        return {"error": e}
    try:
        o = store.update(t, a.get("id"), props, ctx={"now": ctx["now_iso"]})
    except ApiError as e:
        return {"error": e.message, "status": e.status}
    ctx["writes"] += 1
    return {"ok": True, "updated": _props_brief(o, list(props.keys()) + (DEFAULT_PROPS.get(t) or [])[:2])}


def t_associate(a, ctx):
    t = schema.norm_type(a.get("object_type"))
    to = schema.norm_type(a.get("to_type"))
    try:
        if a.get("remove"):
            store.remove_assoc(t, a.get("id"), to, a.get("to_id"))
        else:
            tid = None
            if a.get("primary") and (t, to) in schema.ASSOC and len(schema.ASSOC[(t, to)]) > 1:
                tid = schema.ASSOC[(t, to)][1][0]
            store.add_assoc(t, a.get("id"), to, a.get("to_id"), tid)
    except ApiError as e:
        return {"error": e.message}
    ctx["writes"] += 1
    return {"ok": True}


def t_delete(a, ctx):
    t = schema.norm_type(a.get("object_type"))
    ok = store.archive(t, a.get("id"))
    if ok:
        ctx["writes"] += 1
    return {"ok": ok}


def t_pipelines(a, ctx):
    t = schema.norm_type(a.get("object_type") or "deals")
    return [{"id": p["id"], "label": p["label"], "stages": [{"id": s["id"], "label": s["label"], "closed": s["metadata"].get("isClosed")} for s in p["stages"]]} for p in store.pipelines(t)]


def _users():
    return [json.loads(r[0]) for r in store.rconn().execute("SELECT json FROM owners ORDER BY id")]


def _user(email_or_name):
    k = str(email_or_name or "").strip().lower()
    us = _users()
    for u in us:
        if u["email"].lower() == k:
            return u
    act = [u for u in us if not u.get("archived")]
    for pool in (act, us):
        for u in pool:
            if k and (k == (u["firstName"] + " " + u["lastName"]).lower() or k == (u["lastName"] + " " + u["firstName"]).lower()):
                return u
    return None


def t_users(a, ctx):
    return [{"email": u["email"], "nome": u["firstName"] + " " + u["lastName"], "attivo": not u.get("archived"), "owner_id": u["id"]} for u in _users()]


def _won_stage_ids():
    ids = {"closedwon"}
    for p in store.pipelines("deals"):
        for s in p["stages"]:
            if s["label"].lower() in ("rinnovato", "closed won", "vinta"):
                ids.add(s["id"])
    return ids


def t_revenue(a, ctx):
    cid = a.get("company_id")
    year = int(a.get("year") or 2025)
    won = _won_stage_ids()
    tot = 0.0
    deals = []
    for did, _ in store.get_assocs(cid, "deals"):
        o = store.get_obj("deals", did)
        if not o:
            continue
        p = o["props"]
        if p.get("dealstage") not in won or not p.get("closedate") or not p["closedate"].startswith(str(year)):
            continue
        amt = float(p.get("amount") or 0) * FX.get(p.get("deal_currency_code") or "EUR", 1.0)
        tot += amt
        deals.append({"id": did, "dealname": p.get("dealname"), "amount": p.get("amount"), "currency": p.get("deal_currency_code"), "closedate": p.get("closedate")[:10]})
    return {"company_id": cid, "year": year, "revenue_eur": round(tot + 1e-9, 2), "won_deals": deals[:40], "n_deals": len(deals)}


def t_my_companies(a, ctx):
    email = (a.get("user_email") or ctx["user"]).lower()
    c = store.rconn()
    ids = set()
    for (did,) in c.execute("SELECT id FROM objects WHERE type='deals' AND archived=0 AND lower(json_extract(props,'$.commerciale'))=?", (email,)):
        for cid, _ in store.get_assocs(did, "companies"):
            ids.add(cid)
    for (tid,) in c.execute("SELECT id FROM objects WHERE type='tickets' AND archived=0 AND lower(json_extract(props,'$.assegnatario'))=?", (email,)):
        for cid, _ in store.get_assocs(tid, "companies"):
            ids.add(cid)
    out = []
    for cid in sorted(ids):
        o = store.get_obj("companies", cid)
        if o:
            out.append(_props_brief(o, ["name", "city", "fatturato_2025", "classe_cliente"]))
    return {"total": len(out), "results": out[: int(a.get("limit") or 200)]}


def t_dormant(a, ctx):
    r = store.rconn().execute("SELECT json FROM lists").fetchall()
    for (js,) in r:
        l = json.loads(js)
        if l["name"].lower() == "clienti dormienti":
            ids = [x[0] for x in store.rconn().execute("SELECT obj_id FROM list_members WHERE list_id=? ORDER BY obj_id", (int(l["listId"]),))]
            out = []
            for i in ids:
                o = store.get_obj("companies", i)
                if o:
                    out.append(_props_brief(o, ["name", "city"]))
            return {"total": len(out), "results": out[:300]}
    return {"error": "lista non trovata"}


def _parse_csv(content):
    content = content or ""
    delim = ";" if content.count(";") >= content.count(",") else ","
    return list(csv.DictReader(io.StringIO(content), delimiter=delim))


def t_read_attachment(a, ctx):
    att = _find_att(ctx, a.get("name"))
    if not att:
        return {"error": "allegato non trovato", "disponibili": [x.get("name") for x in ctx["attachments"]]}
    rows = _parse_csv(att.get("content"))
    off = int(a.get("offset") or 0)
    return {"name": att.get("name"), "rows_total": len(rows), "columns": list(rows[0].keys()) if rows else [], "rows": rows[off:off + 60]}


def _find_att(ctx, name):
    atts = ctx["attachments"]
    if not atts:
        return None
    for x in atts:
        if not name or x.get("name") == name:
            return x
    return atts[-1]


def t_apply_price_list(a, ctx):
    from . import migrate as m
    att = _find_att(ctx, a.get("name"))
    if not att:
        return {"error": "allegato non trovato"}
    rows = _parse_csv(att.get("content"))
    created = updated = unchanged = skipped = 0
    details = []
    for r in rows:
        rr = {k.strip().lower(): v for k, v in r.items() if k}
        if m.is_deleted(rr.get("cancellato")):
            skipped += 1
            continue
        sku = m.norm_sku(rr.get("codice_articolo") or rr.get("codice") or rr.get("sku") or rr.get("hs_sku"))
        if not sku:
            skipped += 1
            continue
        price = m.parse_number(rr.get("prezzo_listino") or rr.get("prezzo") or rr.get("price"))
        name = (rr.get("descrizione") or rr.get("name") or "").strip() or None
        ex = store.search("products", {"filterGroups": [{"filters": [{"propertyName": "hs_sku", "operator": "EQ", "value": sku}]}], "limit": 1})[1]
        props = {}
        if price is not None:
            props["price"] = m.num_str(round(price, 2))
        if name:
            props["name"] = name
        if ex:
            o = ex[0]
            diff = {k: v for k, v in props.items() if o["props"].get(k) != v}
            if diff:
                store.update("products", o["id"], diff)
                updated += 1
                if len(details) < 30:
                    details.append({"sku": sku, **diff})
            else:
                unchanged += 1
        else:
            props["hs_sku"] = sku
            store.create("products", props)
            created += 1
    ctx["writes"] += created + updated
    return {"ok": True, "created": created, "updated": updated, "unchanged": unchanged, "skipped": skipped, "examples": details}


TOOLS = {
    "search_records": (t_search, "Cerca record. object_type: companies|contacts|deals|tickets|tasks|notes|calls|emails|meetings|products|line_items. query = testo libero (nome, email, dominio, titolo). filters = [{property, operator (EQ,NEQ,LT,LTE,GT,GTE,BETWEEN,IN,NOT_IN,HAS_PROPERTY,NOT_HAS_PROPERTY,CONTAINS_TOKEN), value|values|highValue}] in AND; per filtrare per record associato usa property 'associations.company' (o .contact/.deal) con value=id.",
                       {"object_type": {"type": "string"}, "query": {"type": "string"}, "filters": {"type": "array", "items": {"type": "object"}},
                        "properties": {"type": "array", "items": {"type": "string"}}, "limit": {"type": "integer"}, "sort_property": {"type": "string"}, "sort_desc": {"type": "boolean"}}, ["object_type"]),
    "get_record": (t_get, "Legge un record per id con tutte le proprietà e gli id dei record associati.",
                   {"object_type": {"type": "string"}, "id": {"type": "string"}}, ["object_type", "id"]),
    "get_associated": (t_assoc, "Elenca i record di tipo to_type associati a un record (es. le trattative di un'azienda, i contatti di un'azienda, le attività di un contatto).",
                       {"object_type": {"type": "string"}, "id": {"type": "string"}, "to_type": {"type": "string"}, "limit": {"type": "integer"}}, ["object_type", "id", "to_type"]),
    "create_record": (t_create, "Crea un record con proprietà e associazioni [{to_type, to_id}].",
                      {"object_type": {"type": "string"}, "properties": {"type": "object"}, "associations": {"type": "array", "items": {"type": "object", "properties": {"to_type": {"type": "string"}, "to_id": {"type": "string"}}}}}, ["object_type", "properties"]),
    "update_record": (t_update, "Aggiorna solo le proprietà indicate di un record. Per svuotare un campo passa stringa vuota.",
                      {"object_type": {"type": "string"}, "id": {"type": "string"}, "properties": {"type": "object"}}, ["object_type", "id", "properties"]),
    "associate": (t_associate, "Crea (o rimuove con remove=true) un'associazione tra due record. primary=true per azienda principale.",
                  {"object_type": {"type": "string"}, "id": {"type": "string"}, "to_type": {"type": "string"}, "to_id": {"type": "string"}, "remove": {"type": "boolean"}, "primary": {"type": "boolean"}}, ["object_type", "id", "to_type", "to_id"]),
    "delete_record": (t_delete, "Archivia (elimina) un record. Usalo solo se esplicitamente richiesto e il record è identificato senza ambiguità.",
                      {"object_type": {"type": "string"}, "id": {"type": "string"}}, ["object_type", "id"]),
    "list_pipelines": (t_pipelines, "Pipeline e fasi (id e label) di deals o tickets.", {"object_type": {"type": "string"}}, []),
    "list_users": (t_users, "Utenti del CRM (commerciali) con email, nome, attivo.", {}, []),
    "revenue": (t_revenue, "Fatturato vinto (EUR) di un'azienda in un anno, con le trattative vinte (Vinta/Rinnovato) chiuse quell'anno, storni inclusi.",
                {"company_id": {"type": "string"}, "year": {"type": "integer"}}, ["company_id", "year"]),
    "my_companies": (t_my_companies, "Aziende seguite da un utente (trattative con commerciale=utente o ticket con assegnatario=utente). Default: chi scrive.",
                     {"user_email": {"type": "string"}, "limit": {"type": "integer"}}, []),
    "dormant_customers": (t_dormant, "Lista 'Clienti dormienti' (aziende con trattative vinte e nessuna attività nel 2025).", {}, []),
    "read_attachment": (t_read_attachment, "Legge le righe di un allegato CSV del messaggio.", {"name": {"type": "string"}, "offset": {"type": "integer"}}, []),
    "apply_price_list": (t_apply_price_list, "Applica un listino CSV allegato ai prodotti: aggiorna prezzo/descrizione per codice (hs_sku), crea gli articoli nuovi.", {"name": {"type": "string"}}, []),
}


def tool_specs():
    out = []
    for name, (fn, desc, props, req) in TOOLS.items():
        out.append({"type": "function", "function": {"name": name, "description": desc,
                                                      "parameters": {"type": "object", "properties": props, "required": req}}})
    return out


# ------------------------------------------------------------------ LLM loop
def _call_llm(messages, tools, timeout):
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY mancante")
    body = {"model": MODEL, "messages": messages, "temperature": 0.1}
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    req = urllib.request.Request(API_URL, data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                                          "HTTP-Referer": "https://brambilla-crm.local", "X-Title": "Brambilla CRM"})
    with urllib.request.urlopen(req, timeout=max(5, timeout)) as r:
        data = json.loads(r.read())
    if "choices" not in data:
        raise RuntimeError(str(data)[:300])
    return data["choices"][0]["message"]


def run(body):
    t0 = time.time()
    ctxin = body.get("context") or {}
    now = store.parse_dt(ctxin.get("now")) or datetime.now(timezone.utc)
    user = (ctxin.get("user") or "").strip().lower()
    u = _user(user) or {}
    ctx = {"now_iso": store.iso_from_dt(now), "user": user, "owner_id": str(u.get("id")) if u.get("id") else None,
           "attachments": [], "writes": 0}
    now_local = ctxin.get("now") or ctx["now_iso"]
    sysmsg = SYSTEM.format(now=f"{now_local} ({['lunedì','martedì','mercoledì','giovedì','venerdì','sabato','domenica'][now.weekday()]})",
                           user=user, user_name=(u.get("firstName", "") + " " + u.get("lastName", "")).strip() or "?")
    msgs = [{"role": "system", "content": sysmsg}]
    for m in body.get("messages") or []:
        role = m.get("role") if m.get("role") in ("user", "assistant") else "user"
        content = m.get("content") or ""
        for att in m.get("attachments") or []:
            ctx["attachments"].append(att)
            c = att.get("content") or ""
            lines = c.splitlines()
            preview = "\n".join(lines[:8])
            content += f"\n\n[Allegato '{att.get('name')}', {max(0, len(lines) - 1)} righe. Anteprima:\n{preview}\n]"
        msgs.append({"role": role, "content": content})
    tools = tool_specs()
    final = None
    for step in range(12):
        remaining = BUDGET_S - (time.time() - t0)
        if remaining < 6:
            break
        try:
            msg = _call_llm(msgs, tools if remaining > 12 else None, remaining - 2)
        except Exception as e:
            print("[agent] llm error", e, flush=True)
            if final is None:
                final = None
            break
        calls = msg.get("tool_calls") or []
        if not calls:
            final = (msg.get("content") or "").strip()
            break
        msgs.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
        for tc in calls:
            name = tc.get("function", {}).get("name")
            try:
                args = json.loads(tc.get("function", {}).get("arguments") or "{}")
            except Exception:
                args = {}
            fn = TOOLS.get(name, (None,))[0]
            try:
                res = fn(args, ctx) if fn else {"error": "strumento sconosciuto"}
            except ApiError as e:
                res = {"error": e.message}
            except Exception as e:
                res = {"error": f"{type(e).__name__}: {e}"}
            out = json.dumps(res, ensure_ascii=False, default=str)
            if len(out) > 12000:
                out = out[:12000] + "…(troncato)"
            print(f"[agent] {name} {json.dumps(args, ensure_ascii=False)[:200]} -> {out[:200]}", flush=True)
            msgs.append({"role": "tool", "tool_call_id": tc.get("id"), "content": out})
    if not final:
        # last attempt without tools
        remaining = BUDGET_S + 5 - (time.time() - t0)
        if remaining > 5:
            try:
                msgs.append({"role": "user", "content": "Rispondi ora al collega con quello che hai (senza usare strumenti)."})
                final = (_call_llm(msgs, None, remaining - 1).get("content") or "").strip()
            except Exception:
                final = None
    if not final:
        final = "Mi dispiace, in questo momento non riesco a completare la richiesta." + (" Alcune modifiche potrebbero essere già state applicate." if ctx["writes"] else "")
    return final

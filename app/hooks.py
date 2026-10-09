"""Automations R10, R11, R12. Called inside the write lock / transaction."""
import json
from datetime import timedelta, datetime, timezone

from . import store

KICKOFF_PREFIX = "Avvio fornitura - "
CALLBACK_PREFIX = "Richiamare: "


def _now(ctx):
    if ctx and ctx.get("now"):
        dt = store.parse_dt(ctx["now"])
        if dt:
            return dt
    return datetime.now(timezone.utc)


def after_write(t, obj, old, ctx=None):
    try:
        if t == "deals":
            _deal(obj, old, ctx)
        elif t == "contacts":
            _contact(obj, old)
    except store.ApiError:
        raise


def _entered(obj, old, stage):
    p = obj["props"]
    if (p.get("pipeline") or "default") != "default" or p.get("dealstage") != stage:
        return False
    if old is None:
        return True
    return old.get("dealstage") != stage or (old.get("pipeline") or "default") != "default"


def _done(oid, kind):
    r = store.wconn.execute("SELECT 1 FROM hooks WHERE obj_id=? AND kind=?", (oid, kind)).fetchone()
    if r:
        return True
    store.wconn.execute("INSERT INTO hooks(obj_id,kind) VALUES(?,?)", (oid, kind))
    return False


def _deal(obj, old, ctx):
    p = obj["props"]
    name = p.get("dealname") or ""
    if _entered(obj, old, "closedwon") and not _done(obj["id"], "kickoff"):
        pl = store.pipeline_by_label("tickets", "Assistenza")
        if pl is None:
            pl = store.pipeline_get("tickets", "0")
        st = store.stage_by_label(pl, "Aperto") or pl["stages"][0]
        tp = {"subject": KICKOFF_PREFIX + name, "hs_pipeline": pl["id"], "hs_pipeline_stage": st["id"],
              "content": f"Avvio fornitura per la trattativa vinta \"{name}\"."}
        if p.get("commerciale"):
            tp["assegnatario"] = p["commerciale"]
        if p.get("hubspot_owner_id"):
            tp["hubspot_owner_id"] = p["hubspot_owner_id"]
        assocs = [{"to": {"id": obj["id"]}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 28}]}]
        for cid, _ in store.get_assocs(obj["id"], "companies", conn=store.wconn):
            assocs.append({"to": {"id": cid}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 339}]})
        store._create_locked("tickets", tp, assocs, ctx, skip_hooks=True)
    if _entered(obj, old, "closedlost") and not _done(obj["id"], "callback"):
        due = _now(ctx) + timedelta(days=180)
        tp = {"hs_task_subject": CALLBACK_PREFIX + name, "hs_timestamp": store.iso_from_dt(due),
              "hs_task_status": "NOT_STARTED", "hs_task_type": "CALL", "hs_task_priority": "MEDIUM",
              "hs_task_body": f"Richiamare il cliente: trattativa \"{name}\" persa."}
        if p.get("hubspot_owner_id"):
            tp["hubspot_owner_id"] = p["hubspot_owner_id"]
        assocs = [{"to": {"id": obj["id"]}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 216}]}]
        store._create_locked("tasks", tp, assocs, ctx, skip_hooks=True)


def company_for_domain(dom, conn=None):
    c = conn or store.wconn
    if not dom:
        return None
    r = c.execute("SELECT id FROM objects WHERE type='companies' AND archived=0 AND json_extract(props,'$.domain') = ? COLLATE NOCASE ORDER BY id LIMIT 1", (dom,)).fetchone()
    if r:
        return r[0]
    r = c.execute("SELECT id FROM objects WHERE type='companies' AND archived=0 AND (';'||lower(json_extract(props,'$.hs_additional_domains'))||';') LIKE ? ORDER BY id LIMIT 1", (f"%;{dom.lower()};%",)).fetchone()
    return r[0] if r else None


def _contact(obj, old):
    email = obj["props"].get("email")
    if not email or "@" not in email:
        return
    if old is not None and old.get("email") == email:
        return
    if store.wconn.execute("SELECT 1 FROM assoc WHERE from_id=? AND to_type='companies' LIMIT 1", (obj["id"],)).fetchone():
        return
    dom = store.clean_domain(email.split("@")[-1])
    cid = company_for_domain(dom)
    if cid:
        store.add_assoc_locked("contacts", obj["id"], "companies", cid, 1)
        obj["props"]["associatedcompanyid"] = str(cid)

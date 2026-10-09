"""SQLite-backed object store with HubSpot semantics."""
import json
import os
import re
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone, timedelta

from . import schema

DATA_DIR = os.environ.get("DATA_DIR") or ("/data" if os.path.isdir("/data") else os.path.join(os.path.dirname(__file__), "..", "data"))
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "crm.sqlite3")

W = threading.RLock()
_local = threading.local()


class ApiError(Exception):
    def __init__(self, status, message, category="VALIDATION_ERROR", **extra):
        super().__init__(message)
        self.status = status
        self.message = message
        self.category = category
        self.extra = extra

    def body(self):
        b = {"status": "error", "message": self.message, "correlationId": str(uuid.uuid4()),
             "category": self.category}
        b.update(self.extra)
        return b


def not_found(msg="resource not found"):
    return ApiError(404, msg, "OBJECT_NOT_FOUND")


def _connect():
    c = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30, isolation_level=None)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    c.execute("PRAGMA busy_timeout=30000")
    c.execute("PRAGMA cache_size=-200000")
    c.execute("PRAGMA temp_store=MEMORY")
    c.execute("PRAGMA mmap_size=1073741824")
    return c


wconn = _connect()


def rconn():
    c = getattr(_local, "c", None)
    if c is None:
        c = _connect()
        _local.c = c
    return c


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS objects(id INTEGER PRIMARY KEY, type TEXT NOT NULL, props TEXT NOT NULL,
  created TEXT NOT NULL, updated TEXT NOT NULL, archived INTEGER NOT NULL DEFAULT 0, archived_at TEXT);
CREATE INDEX IF NOT EXISTS ix_obj_type ON objects(type, archived, id);
CREATE INDEX IF NOT EXISTS ix_obj_legacy2 ON objects(type, json_extract(props,'$.id_legacy') COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS ix_obj_email ON objects(type, json_extract(props,'$.email') COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS ix_obj_domain ON objects(type, json_extract(props,'$.domain') COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS ix_obj_name ON objects(type, json_extract(props,'$.name') COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS ix_obj_dealname ON objects(type, json_extract(props,'$.dealname') COLLATE NOCASE);
CREATE TABLE IF NOT EXISTS assoc(from_id INTEGER NOT NULL, to_id INTEGER NOT NULL, from_type TEXT NOT NULL,
  to_type TEXT NOT NULL, type_id INTEGER NOT NULL, category TEXT NOT NULL DEFAULT 'HUBSPOT_DEFINED',
  PRIMARY KEY(from_id, to_id, type_id)) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS ix_assoc_ft ON assoc(from_id, to_type);
CREATE TABLE IF NOT EXISTS uniq(type TEXT, prop TEXT, value TEXT, obj_id INTEGER, PRIMARY KEY(type, prop, value)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS propdefs(type TEXT, name TEXT, json TEXT, PRIMARY KEY(type, name));
CREATE TABLE IF NOT EXISTS propgroups(type TEXT, name TEXT, json TEXT, PRIMARY KEY(type, name));
CREATE TABLE IF NOT EXISTS pipelines(type TEXT, id TEXT, json TEXT, PRIMARY KEY(type, id));
CREATE TABLE IF NOT EXISTS lists(id INTEGER PRIMARY KEY, json TEXT);
CREATE TABLE IF NOT EXISTS list_members(list_id INTEGER, obj_id INTEGER, ts TEXT, PRIMARY KEY(list_id, obj_id)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS hooks(obj_id INTEGER, kind TEXT, PRIMARY KEY(obj_id, kind)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS owners(id INTEGER PRIMARY KEY, email TEXT, json TEXT);
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS labels(from_type TEXT, to_type TEXT, type_id INTEGER, label TEXT, category TEXT, PRIMARY KEY(from_type,to_type,type_id));
CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, json TEXT);
"""


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (datetime.now(timezone.utc).microsecond // 1000)


def iso_from_dt(dt):
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (dt.microsecond // 1000)


def parse_dt(v):
    """Parse ISO/ms/date into aware datetime (UTC) or None."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v / 1000.0, tz=timezone.utc)
    s = str(v).strip()
    if re.fullmatch(r"-?\d{9,}", s):
        return datetime.fromtimestamp(int(s) / 1000.0, tz=timezone.utc)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    try:
        s2 = s.replace("Z", "+00:00").replace(" ", "T")
        dt = datetime.fromisoformat(s2)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


# ---------------------------------------------------------------- property definitions
_defs_cache = {}


def defs(t):
    d = _defs_cache.get(t)
    if d is None:
        d = {}
        for name, js in rconn().execute("SELECT name, json FROM propdefs WHERE type=?", (t,)):
            d[name] = json.loads(js)
        _defs_cache[t] = d
    return d


def invalidate_defs():
    _defs_cache.clear()


def unique_props(t):
    u = [n for n, p in defs(t).items() if p.get("hasUniqueValue")]
    if t == "contacts":
        u.append("email")
    return u


READ_ONLY = {"hs_object_id", "hs_lastmodifieddate", "lastmodifieddate"}
NUM_RE = re.compile(r"^-?\d+(\.\d+)?([eE][-+]?\d+)?$")


def norm_value(t, name, value, pdef):
    if value is None:
        return None
    if isinstance(value, bool):
        value = "true" if value else "false"
    if isinstance(value, (list, dict)):
        value = json.dumps(value)
    s = str(value) if not isinstance(value, float) else repr(value)
    if isinstance(value, float) and value.is_integer():
        s = str(int(value))
    if s == "":
        return None
    typ = pdef.get("type") if pdef else "string"
    if typ == "number":
        s2 = s.strip()
        if not NUM_RE.match(s2):
            raise ApiError(400, f"Property values were not valid: {name}={s!r} is not a valid number",
                           "VALIDATION_ERROR", errors=[{"message": f"{s} is not a valid number", "code": "INVALID_FLOAT", "context": {"propertyName": [name]}}])
        return s2
    if typ == "datetime":
        dt = parse_dt(s)
        if dt is None:
            raise ApiError(400, f"Property values were not valid: {name}={s!r} is not a valid datetime", "VALIDATION_ERROR")
        return iso_from_dt(dt)
    if typ == "date":
        dt = parse_dt(s)
        if dt is None:
            raise ApiError(400, f"Property values were not valid: {name}={s!r} is not a valid date", "VALIDATION_ERROR")
        return dt.strftime("%Y-%m-%d")
    if typ == "bool":
        return "true" if s.lower() in ("true", "1", "yes") else "false"
    if name == "email" and t == "contacts":
        return s.strip().lower()
    if name == "partita_iva":
        d = re.sub(r"\D", "", s)
        return d or s.strip()
    if name == "domain" and t == "companies":
        return clean_domain(s) or s.strip()
    return s


def clean_domain(s):
    if not s:
        return None
    s = str(s).strip().lower()
    s = re.sub(r"^[a-z]+://", "", s)
    s = s.split("/")[0].split("?")[0].split("#")[0]
    s = s.split("@")[-1]
    s = s.split(":")[0]
    if s.startswith("www."):
        s = s[4:]
    s = s.strip(". ")
    return s or None


def prepare_props(t, props, partial=False):
    """Validate+normalize incoming props. Returns dict name->str|None."""
    if props is None:
        return {}
    if not isinstance(props, dict):
        raise ApiError(400, "Invalid input JSON: properties must be an object", "VALIDATION_ERROR")
    d = defs(t)
    out = {}
    bad = []
    for k, v in props.items():
        if k in READ_ONLY:
            continue
        pdef = d.get(k)
        if pdef is None:
            bad.append(k)
            continue
        out[k] = norm_value(t, k, v, pdef)
    if bad:
        errs = [{"isValid": False, "message": f'Property "{b}" does not exist', "error": "PROPERTY_DOESNT_EXIST", "name": b} for b in bad]
        raise ApiError(400, "Property values were not valid: " + json.dumps(errs), "VALIDATION_ERROR",
                       errors=[{"message": f'Property "{b}" does not exist', "code": "PROPERTY_DOESNT_EXIST", "context": {"propertyName": [b]}} for b in bad])
    return out


# ---------------------------------------------------------------- id sequence
_seq = {"next": None}


def next_id(n=1):
    with W:
        if _seq["next"] is None:
            r = wconn.execute("SELECT v FROM meta WHERE k='seq'").fetchone()
            m = wconn.execute("SELECT max(id) FROM objects").fetchone()[0] or 0
            _seq["next"] = max(int(r[0]) if r else 0, m + 1, 1000001)
        first = _seq["next"]
        _seq["next"] += n
        wconn.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('seq',?)", (str(_seq["next"]),))
        return first


# ---------------------------------------------------------------- objects
def _row_to_obj(row):
    id_, typ, props, created, updated, archived, archived_at = row
    return {"id": id_, "type": typ, "props": json.loads(props), "created": created, "updated": updated,
            "archived": bool(archived), "archived_at": archived_at}


def get_obj(t, oid, include_archived=False, conn=None):
    try:
        oid = int(oid)
    except (TypeError, ValueError):
        return None
    c = conn or rconn()
    row = c.execute("SELECT id,type,props,created,updated,archived,archived_at FROM objects WHERE id=? AND type=?", (oid, t)).fetchone()
    if not row:
        return None
    o = _row_to_obj(row)
    if o["archived"] and not include_archived:
        return None
    return o


def find_by_prop(t, prop, value, conn=None):
    c = conn or rconn()
    if value is None:
        return None
    if prop in ("hs_object_id", "id"):
        return get_obj(t, value, conn=c)
    pdef = defs(t).get(prop)
    v = norm_value(t, prop, value, pdef) if pdef else str(value)
    if prop in unique_props(t):
        r = c.execute("SELECT obj_id FROM uniq WHERE type=? AND prop=? AND value=?", (t, prop, uval(v))).fetchone()
        return get_obj(t, r[0], conn=c) if r else None
    row = c.execute(f"SELECT id,type,props,created,updated,archived,archived_at FROM objects WHERE type=? AND archived=0 AND json_extract(props,'$.{_jpath(prop)}') = ? COLLATE NOCASE ORDER BY id LIMIT 1", (t, v)).fetchone()
    return _row_to_obj(row) if row else None


def uval(v):
    return str(v).strip().lower()


def _jpath(p):
    _safe(p)
    return p if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", p) else '"' + p + '"'


def _safe(p):
    if not re.fullmatch(r"[A-Za-z0-9_\-\.]+", p or ""):
        raise ApiError(400, f"Invalid property name {p!r}", "VALIDATION_ERROR")
    return p


def _check_unique(t, props, self_id=None):
    for up in unique_props(t):
        v = props.get(up)
        if v:
            r = wconn.execute("SELECT obj_id FROM uniq WHERE type=? AND prop=? AND value=?", (t, up, uval(v))).fetchone()
            if r and r[0] != self_id:
                if t == "contacts" and up == "email":
                    raise ApiError(409, f"Contact already exists. Existing ID: {r[0]}", "CONFLICT")
                raise ApiError(409, f"A {schema.SINGULAR_OF.get(t, t)} with {up}={v} already exists. Existing ID: {r[0]}", "CONFLICT",
                               context={"id": [str(r[0])]})


def _set_unique(t, oid, old, new):
    for up in unique_props(t):
        ov, nv = (old or {}).get(up), new.get(up)
        if ov == nv:
            continue
        if ov:
            wconn.execute("DELETE FROM uniq WHERE type=? AND prop=? AND value=? AND obj_id=?", (t, up, uval(ov), oid))
        if nv:
            wconn.execute("INSERT OR REPLACE INTO uniq(type,prop,value,obj_id) VALUES(?,?,?,?)", (t, up, uval(nv), oid))


def create(t, props, associations=None, ctx=None, skip_hooks=False):
    p = prepare_props(t, props)
    with W:
        wconn.execute("BEGIN IMMEDIATE")
        try:
            obj = _create_locked(t, p, associations, ctx, skip_hooks)
            wconn.execute("COMMIT")
        except Exception:
            wconn.execute("ROLLBACK")
            raise
    return obj


def _create_locked(t, p, associations=None, ctx=None, skip_hooks=False):
    p = {k: v for k, v in p.items() if v is not None}
    _check_unique(t, p)
    oid = next_id()
    ts = now_iso()
    created = p.get("createdate") or ts
    p["createdate"] = created
    p["hs_lastmodifieddate"] = ts
    if t == "contacts":
        p["lastmodifieddate"] = ts
    _defaults_on_create(t, p)
    wconn.execute("INSERT INTO objects(id,type,props,created,updated,archived) VALUES(?,?,?,?,?,0)",
                  (oid, t, json.dumps(p, ensure_ascii=False), created, ts))
    _set_unique(t, oid, None, p)
    for a in associations or []:
        to = a.get("to") or {}
        to_id = to.get("id")
        types = a.get("types") or [{}]
        to_type = _type_of(to_id)
        if to_type is None:
            raise ApiError(400, f"Association target {to_id} does not exist", "VALIDATION_ERROR")
        for ty in types:
            tid = ty.get("associationTypeId")
            add_assoc_locked(t, oid, to_type, int(to_id), int(tid) if tid else None, ty.get("associationCategory") or "HUBSPOT_DEFINED")
    obj = {"id": oid, "type": t, "props": p, "created": created, "updated": ts, "archived": False, "archived_at": None}
    if not skip_hooks:
        from . import hooks
        hooks.after_write(t, obj, None, ctx)
    return obj


def _defaults_on_create(t, p):
    if t == "deals":
        if not p.get("pipeline"):
            p["pipeline"] = "default"
        if not p.get("dealstage"):
            pl = pipeline_get("deals", p["pipeline"])
            if pl and pl["stages"]:
                p["dealstage"] = pl["stages"][0]["id"]
    if t == "tickets":
        if not p.get("hs_pipeline"):
            p["hs_pipeline"] = "0"
        if not p.get("hs_pipeline_stage"):
            pl = pipeline_get("tickets", p["hs_pipeline"])
            if pl and pl["stages"]:
                p["hs_pipeline_stage"] = pl["stages"][0]["id"]
    if t == "line_items" and "amount" not in p:
        try:
            q = float(p.get("quantity") or 1)
            pr = float(p.get("price") or 0)
            disc = float(p.get("hs_discount_percentage") or 0)
            p["amount"] = fmt_num(round(q * pr * (1 - disc / 100.0), 2))
        except ValueError:
            pass


def fmt_num(x):
    if x is None:
        return None
    if float(x).is_integer():
        return str(int(x))
    return ("%.2f" % x).rstrip("0").rstrip(".") if abs(x - round(x, 2)) < 1e-9 else repr(x)


def _type_of(oid):
    try:
        r = wconn.execute("SELECT type FROM objects WHERE id=? AND archived=0", (int(oid),)).fetchone()
    except (TypeError, ValueError):
        return None
    return r[0] if r else None


def update(t, oid, props, id_property=None, ctx=None):
    p = prepare_props(t, props)
    with W:
        wconn.execute("BEGIN IMMEDIATE")
        try:
            obj = _update_locked(t, oid, p, id_property, ctx)
            wconn.execute("COMMIT")
        except Exception:
            wconn.execute("ROLLBACK")
            raise
    return obj


def _update_locked(t, oid, p, id_property=None, ctx=None):
    if id_property and id_property not in ("hs_object_id", "id"):
        cur = find_by_prop(t, id_property, oid, conn=wconn)
    else:
        cur = get_obj(t, oid, conn=wconn)
    if cur is None:
        raise not_found(f"Object not found. objectId are usually numeric.")
    old = dict(cur["props"])
    new = dict(old)
    for k, v in p.items():
        if v is None:
            new.pop(k, None)
        else:
            new[k] = v
    _check_unique(t, new, self_id=cur["id"])
    ts = now_iso()
    new["hs_lastmodifieddate"] = ts
    if t == "contacts":
        new["lastmodifieddate"] = ts
    if t == "line_items" and any(k in p for k in ("quantity", "price", "hs_discount_percentage")) and "amount" not in p:
        new.pop("amount", None)
        _defaults_on_create(t, new)
    wconn.execute("UPDATE objects SET props=?, updated=? WHERE id=?", (json.dumps(new, ensure_ascii=False), ts, cur["id"]))
    _set_unique(t, cur["id"], old, new)
    obj = dict(cur, props=new, updated=ts)
    from . import hooks
    hooks.after_write(t, obj, old, ctx)
    return obj


def archive(t, oid):
    with W:
        cur = get_obj(t, oid, conn=wconn)
        if cur is None:
            return False
        wconn.execute("BEGIN IMMEDIATE")
        ts = now_iso()
        wconn.execute("UPDATE objects SET archived=1, archived_at=? WHERE id=?", (ts, cur["id"]))
        _set_unique(t, cur["id"], cur["props"], {})
        wconn.execute("DELETE FROM assoc WHERE from_id=? OR to_id=?", (cur["id"], cur["id"]))
        wconn.execute("DELETE FROM list_members WHERE obj_id=?", (cur["id"],))
        wconn.execute("COMMIT")
        return True


def merge(t, primary_id, merge_id):
    with W:
        a = get_obj(t, primary_id, conn=wconn)
        b = get_obj(t, merge_id, conn=wconn)
        if not a or not b:
            raise not_found()
        wconn.execute("BEGIN IMMEDIATE")
        try:
            newp = dict(b["props"])
            newp.update({k: v for k, v in a["props"].items() if v not in (None, "")})
            _set_unique(t, b["id"], b["props"], {})
            if t == "companies":
                doms = set(filter(None, (a["props"].get("hs_additional_domains") or "").split(";")))
                doms |= set(filter(None, (b["props"].get("hs_additional_domains") or "").split(";")))
                if b["props"].get("domain") and b["props"].get("domain") != newp.get("domain"):
                    doms.add(b["props"]["domain"])
                doms.discard(newp.get("domain"))
                if doms:
                    newp["hs_additional_domains"] = ";".join(sorted(doms))
            if t == "contacts" and b["props"].get("email") and b["props"].get("email") != newp.get("email"):
                extra = set(filter(None, (newp.get("hs_additional_emails") or "").split(";")))
                extra.add(b["props"]["email"])
                newp["hs_additional_emails"] = ";".join(sorted(extra))
            newp["hs_lastmodifieddate"] = now_iso()
            wconn.execute("UPDATE objects SET props=? WHERE id=?", (json.dumps(newp, ensure_ascii=False), a["id"]))
            _set_unique(t, a["id"], a["props"], newp)
            for (to_id, to_type, tid, cat) in wconn.execute("SELECT to_id,to_type,type_id,category FROM assoc WHERE from_id=?", (b["id"],)).fetchall():
                if to_id != a["id"]:
                    add_assoc_locked(t, a["id"], to_type, to_id, tid, cat)
            wconn.execute("DELETE FROM assoc WHERE from_id=? OR to_id=?", (b["id"],) * 2)
            wconn.execute("UPDATE objects SET archived=1, archived_at=? WHERE id=?", (now_iso(), b["id"]))
            wconn.execute("COMMIT")
        except Exception:
            wconn.execute("ROLLBACK")
            raise
        return get_obj(t, a["id"], conn=wconn)


# ---------------------------------------------------------------- associations
def add_assoc_locked(f_type, f_id, t_type, t_id, type_id=None, category="HUBSPOT_DEFINED"):
    if type_id is None:
        type_id = schema.default_assoc_type(f_type, t_type)
        if type_id is None:
            type_id = 0
    rev = schema.reverse_type_id(f_type, t_type, type_id) if category == "HUBSPOT_DEFINED" else _user_label_rev(f_type, t_type, type_id)
    wconn.execute("INSERT OR IGNORE INTO assoc(from_id,to_id,from_type,to_type,type_id,category) VALUES(?,?,?,?,?,?)",
                  (f_id, t_id, f_type, t_type, type_id, category))
    wconn.execute("INSERT OR IGNORE INTO assoc(from_id,to_id,from_type,to_type,type_id,category) VALUES(?,?,?,?,?,?)",
                  (t_id, f_id, t_type, f_type, rev if rev is not None else type_id, category))
    # primary label implies unlabeled default too
    d = schema.default_assoc_type(f_type, t_type)
    if d is not None and type_id != d and category == "HUBSPOT_DEFINED":
        rd = schema.default_assoc_type(t_type, f_type)
        wconn.execute("INSERT OR IGNORE INTO assoc VALUES(?,?,?,?,?,?)", (f_id, t_id, f_type, t_type, d, "HUBSPOT_DEFINED"))
        if rd is not None:
            wconn.execute("INSERT OR IGNORE INTO assoc VALUES(?,?,?,?,?,?)", (t_id, f_id, t_type, f_type, rd, "HUBSPOT_DEFINED"))
    if (f_type, t_type) == ("contacts", "companies") and type_id == 1:
        _set_prop_locked(f_id, "associatedcompanyid", str(t_id))
    if (t_type, f_type) == ("contacts", "companies") and rev == 1:
        _set_prop_locked(t_id, "associatedcompanyid", str(f_id))


def _set_prop_locked(oid, k, v):
    r = wconn.execute("SELECT props FROM objects WHERE id=?", (oid,)).fetchone()
    if r:
        p = json.loads(r[0])
        if p.get(k) != v:
            p[k] = v
            wconn.execute("UPDATE objects SET props=? WHERE id=?", (json.dumps(p, ensure_ascii=False), oid))


def _user_label_rev(f, t, type_id):
    return type_id


def add_assoc(f_type, f_id, t_type, t_id, type_id=None, category="HUBSPOT_DEFINED", ctx=None):
    with W:
        if not get_obj(f_type, f_id, conn=wconn):
            raise not_found(f"{schema.SINGULAR_OF.get(f_type, f_type)} {f_id} not found")
        if not get_obj(t_type, t_id, conn=wconn):
            raise not_found(f"{schema.SINGULAR_OF.get(t_type, t_type)} {t_id} not found")
        wconn.execute("BEGIN IMMEDIATE")
        try:
            add_assoc_locked(f_type, int(f_id), t_type, int(t_id), type_id, category)
            wconn.execute("COMMIT")
        except Exception:
            wconn.execute("ROLLBACK")
            raise


def remove_assoc(f_type, f_id, t_type, t_id, type_id=None):
    with W:
        if type_id is None:
            wconn.execute("DELETE FROM assoc WHERE from_id=? AND to_id=?", (int(f_id), int(t_id)))
            wconn.execute("DELETE FROM assoc WHERE from_id=? AND to_id=?", (int(t_id), int(f_id)))
        else:
            rev = schema.reverse_type_id(f_type, t_type, type_id)
            wconn.execute("DELETE FROM assoc WHERE from_id=? AND to_id=? AND type_id=?", (int(f_id), int(t_id), type_id))
            wconn.execute("DELETE FROM assoc WHERE from_id=? AND to_id=? AND type_id=?", (int(t_id), int(f_id), rev))
        if (f_type, t_type) == ("contacts", "companies"):
            _fix_primary(int(f_id))
        if (t_type, f_type) == ("contacts", "companies"):
            _fix_primary(int(t_id))


def _fix_primary(cid):
    r = wconn.execute("SELECT to_id FROM assoc WHERE from_id=? AND to_type='companies' AND type_id=1", (cid,)).fetchone()
    row = wconn.execute("SELECT props FROM objects WHERE id=?", (cid,)).fetchone()
    if not row:
        return
    p = json.loads(row[0])
    if r:
        p["associatedcompanyid"] = str(r[0])
    else:
        p.pop("associatedcompanyid", None)
    wconn.execute("UPDATE objects SET props=? WHERE id=?", (json.dumps(p, ensure_ascii=False), cid))


def get_assocs(f_id, to_type, conn=None):
    """Return ordered list of (to_id, [(category, type_id, label)])."""
    c = conn or rconn()
    out = {}
    for to_id, tid, cat in c.execute("SELECT a.to_id, a.type_id, a.category FROM assoc a JOIN objects o ON o.id=a.to_id AND o.archived=0 WHERE a.from_id=? AND a.to_type=? ORDER BY a.to_id", (int(f_id), to_type)):
        out.setdefault(to_id, []).append((cat, tid, label_for(tid, cat)))
    return list(out.items())


def label_for(tid, cat):
    if cat == "USER_DEFINED":
        r = rconn().execute("SELECT label FROM labels WHERE type_id=?", (tid,)).fetchone()
        return r[0] if r else None
    return schema.assoc_label(tid)


# ---------------------------------------------------------------- API serialization
def to_api(obj, properties=None, associations=None, with_history=False):
    p = obj["props"]
    if properties:
        props = {k: p.get(k) for k in properties}
        for k in ("hs_object_id", "createdate", "hs_lastmodifieddate"):
            props.setdefault(k, p.get(k))
        if obj["type"] == "contacts":
            props.setdefault("lastmodifieddate", p.get("lastmodifieddate"))
    else:
        props = dict(p)
    if "hs_object_id" in props or not properties:
        props["hs_object_id"] = str(obj["id"])
    res = {"id": str(obj["id"]), "properties": props, "createdAt": obj["created"], "updatedAt": obj["updated"],
           "archived": obj["archived"]}
    if obj["archived"]:
        res["archivedAt"] = obj.get("archived_at")
    if associations:
        assoc = {}
        for at in associations:
            nt = schema.norm_type(at)
            if not nt:
                continue
            lst = get_assocs(obj["id"], nt)
            if lst:
                results = []
                for to_id, types in lst:
                    for cat, tid, label in types:
                        results.append({"id": str(to_id), "type": schema.assoc_type_name(obj["type"], nt) + ("" if not label else "_" + label.lower())})
                assoc[at] = {"results": results}
        if assoc:
            res["associations"] = assoc
    return res


# ---------------------------------------------------------------- search
SEARCH_DEFAULT = {
    "contacts": ["firstname", "lastname", "email", "phone", "company", "hs_additional_emails"],
    "companies": ["name", "domain", "website", "phone", "hs_additional_domains"],
    "deals": ["dealname"], "tickets": ["subject", "content"], "products": ["name", "hs_sku", "description"],
    "line_items": ["name"], "quotes": ["hs_title"], "notes": ["hs_note_body"], "calls": ["hs_call_title", "hs_call_body"],
    "emails": ["hs_email_subject", "hs_email_text"], "meetings": ["hs_meeting_title", "hs_meeting_body"],
    "tasks": ["hs_task_subject", "hs_task_body"],
}


def _jx(prop):
    if prop in ("hs_object_id", "id"):
        return "o.id"
    return f"json_extract(o.props,'$.{_jpath(prop)}')"


def _filter_sql(t, f, args):
    prop = f.get("propertyName")
    op = (f.get("operator") or "EQ").upper()
    if not prop:
        raise ApiError(400, "filter propertyName is required", "VALIDATION_ERROR")
    if prop.startswith("associations."):
        at = schema.norm_type(prop.split(".", 1)[1])
        vals = f.get("values") or ([f.get("value")] if f.get("value") is not None else [])
        ph = ",".join("?" * len(vals)) or "NULL"
        args.extend([at] + [int(v) for v in vals])
        sub = f"EXISTS(SELECT 1 FROM assoc a WHERE a.from_id=o.id AND a.to_type=? AND a.to_id IN ({ph}))"
        return sub if op in ("EQ", "IN") else "NOT " + sub
    pdef = defs(t).get(prop) or {}
    typ = pdef.get("type", "string")
    if prop in ("hs_object_id", "id"):
        typ = "number"
    if prop in ("createdate", "hs_lastmodifieddate", "lastmodifieddate"):
        typ = "datetime"
    x = _jx(prop)

    def conv(v):
        if v is None:
            return None
        if typ == "number":
            try:
                return float(v)
            except (TypeError, ValueError):
                return str(v)
        if typ in ("datetime", "date"):
            dt = parse_dt(v)
            if dt is None:
                return str(v)
            return iso_from_dt(dt) if typ == "datetime" else dt.strftime("%Y-%m-%d")
        if isinstance(v, bool):
            return "true" if v else "false"
        return str(v)

    xx = f"CAST({x} AS REAL)" if typ == "number" and prop not in ("hs_object_id", "id") else x
    coll = " COLLATE NOCASE" if typ not in ("number", "datetime", "date") else ""
    if op == "HAS_PROPERTY":
        return f"({x} IS NOT NULL AND {x} != '')"
    if op == "NOT_HAS_PROPERTY":
        return f"({x} IS NULL OR {x} = '')"
    if op in ("EQ", "NEQ", "LT", "LTE", "GT", "GTE"):
        v = conv(f.get("value"))
        sym = {"EQ": "=", "NEQ": "!=", "LT": "<", "LTE": "<=", "GT": ">", "GTE": ">="}[op]
        if typ == "datetime" and op in ("EQ", "NEQ") and isinstance(v, str) and len(v) >= 10:
            # equality at ms precision
            pass
        args.append(v)
        if op == "NEQ":
            return f"({x} IS NULL OR {xx} != ?{coll})"
        if typ == "enumeration" and op == "EQ" and pdef.get("fieldType") == "checkbox":
            args.pop()
            args.extend([v, "%;" + str(v) + ";%"])
            return f"({x} = ?{coll} OR (';'||{x}||';') LIKE ?)"
        return f"({x} IS NOT NULL AND {xx} {sym} ?{coll})"
    if op == "BETWEEN":
        args.extend([conv(f.get("value")), conv(f.get("highValue"))])
        return f"({x} IS NOT NULL AND {xx} >= ? AND {xx} <= ?)"
    if op in ("IN", "NOT_IN"):
        vals = [conv(v) for v in (f.get("values") or [])]
        if not vals:
            return "0" if op == "IN" else "1"
        args.extend(vals)
        ph = ",".join("?" * len(vals))
        if op == "IN":
            return f"({xx}{coll} IN ({ph}))"
        return f"({x} IS NULL OR {xx}{coll} NOT IN ({ph}))"
    if op in ("CONTAINS_TOKEN", "NOT_CONTAINS_TOKEN"):
        v = str(f.get("value") or "").replace("*", "%")
        args.append(f"%{v}%")
        if op == "CONTAINS_TOKEN":
            return f"({x} LIKE ?)"
        return f"({x} IS NULL OR {x} NOT LIKE ?)"
    raise ApiError(400, f"Unsupported operator {op}", "VALIDATION_ERROR")


def search(t, body):
    body = body or {}
    args = [t]
    where = ["o.type=?", "o.archived=0"]
    groups = body.get("filterGroups") or []
    if len(groups) > 5:
        raise ApiError(400, "Too many filter groups (max 5)", "VALIDATION_ERROR")
    gsql = []
    for g in groups:
        fl = g.get("filters") or []
        if len(fl) > 6:
            raise ApiError(400, "Too many filters in group (max 6)", "VALIDATION_ERROR")
        parts = [_filter_sql(t, f, args) for f in fl]
        if parts:
            gsql.append("(" + " AND ".join(parts) + ")")
    if gsql:
        where.append("(" + " OR ".join(gsql) + ")")
    q = body.get("query")
    if q:
        cols = SEARCH_DEFAULT.get(t, ["name"])
        ors = []
        for token in str(q).split():
            ors_t = []
            for ccol in cols:
                ors_t.append(f"{_jx(ccol)} LIKE ?")
                args.append(f"%{token.replace('*', '')}%")
            ors.append("(" + " OR ".join(ors_t) + ")")
        if ors:
            where.append("(" + " AND ".join(ors) + ")")
    order = []
    for s in body.get("sorts") or []:
        if isinstance(s, str):
            d = "DESC" if s.startswith("-") else "ASC"
            p = s.lstrip("-")
        else:
            p = s.get("propertyName")
            d = "DESC" if str(s.get("direction", "ASCENDING")).upper().startswith("DESC") else "ASC"
        if not p:
            continue
        pdef = defs(t).get(p) or {}
        x = _jx(p)
        if pdef.get("type") == "number":
            x = f"CAST({x} AS REAL)"
        order.append(f"{x} {d}")
    order.append("o.id ASC")
    limit = body.get("limit", 10)
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 10
    if limit > 200:
        raise ApiError(400, "limit must be <= 200", "VALIDATION_ERROR")
    limit = max(0, limit)
    try:
        offset = int(body.get("after") or 0)
    except (TypeError, ValueError):
        offset = 0
    wsql = " AND ".join(where)
    c = rconn()
    total = c.execute(f"SELECT count(*) FROM objects o WHERE {wsql}", args).fetchone()[0]
    rows = c.execute(f"SELECT o.id,o.type,o.props,o.created,o.updated,o.archived,o.archived_at FROM objects o WHERE {wsql} ORDER BY {', '.join(order)} LIMIT ? OFFSET ?",
                     args + [limit, offset]).fetchall()
    objs = [_row_to_obj(r) for r in rows]
    nxt = offset + len(objs)
    return total, objs, (str(nxt) if nxt < total else None)


def list_objects(t, limit=10, after=None, archived=False):
    try:
        after = int(after) if after else 0
    except ValueError:
        after = 0
    rows = rconn().execute("SELECT id,type,props,created,updated,archived,archived_at FROM objects WHERE type=? AND archived=? AND id>? ORDER BY id LIMIT ?",
                           (t, 1 if archived else 0, after, limit + 1)).fetchall()
    objs = [_row_to_obj(r) for r in rows[:limit]]
    nxt = str(objs[-1]["id"]) if len(rows) > limit and objs else None
    return objs, nxt


# ---------------------------------------------------------------- pipelines
_pl_cache = {}


def pipelines(t):
    if t not in _pl_cache:
        rows = rconn().execute("SELECT json FROM pipelines WHERE type=?", (t,)).fetchall()
        lst = [json.loads(r[0]) for r in rows]
        lst.sort(key=lambda p: (p.get("displayOrder", 0), p.get("label")))
        _pl_cache[t] = lst
    return _pl_cache[t]


def pipeline_get(t, pid):
    for p in pipelines(t):
        if p["id"] == str(pid):
            return p
    return None


def pipeline_by_label(t, label):
    for p in pipelines(t):
        if p["label"].strip().lower() == label.strip().lower():
            return p
    return None


def stage_by_label(pl, label):
    for s in pl["stages"]:
        if s["label"].strip().lower() == label.strip().lower():
            return s
    return None


def pipeline_save(t, pl):
    with W:
        wconn.execute("INSERT OR REPLACE INTO pipelines(type,id,json) VALUES(?,?,?)", (t, pl["id"], json.dumps(pl, ensure_ascii=False)))
    _pl_cache.pop(t, None)


def pipeline_delete(t, pid):
    with W:
        wconn.execute("DELETE FROM pipelines WHERE type=? AND id=?", (t, pid))
    _pl_cache.pop(t, None)


def new_small_id():
    return str(next_id())


# ---------------------------------------------------------------- property defs mgmt
def save_propdef(t, pdef):
    with W:
        wconn.execute("INSERT OR REPLACE INTO propdefs(type,name,json) VALUES(?,?,?)", (t, pdef["name"], json.dumps(pdef, ensure_ascii=False)))
    invalidate_defs()


def delete_propdef(t, name):
    with W:
        wconn.execute("DELETE FROM propdefs WHERE type=? AND name=?", (t, name))
    invalidate_defs()


# ---------------------------------------------------------------- reset / init
def init_db():
    with W:
        wconn.executescript(SCHEMA_SQL)
        n = wconn.execute("SELECT count(*) FROM propdefs").fetchone()[0]
    if n == 0:
        seed()


def seed():
    ts = now_iso()
    with W:
        wconn.execute("BEGIN IMMEDIATE")
        for t in schema.OBJECT_TYPES:
            for i, p in enumerate(schema.default_properties(t)):
                p = dict(p, createdAt=ts, updatedAt=ts, archived=False, displayOrder=i)
                wconn.execute("INSERT OR REPLACE INTO propdefs(type,name,json) VALUES(?,?,?)", (t, p["name"], json.dumps(p)))
            for g, label in schema.GROUPS[t]:
                wconn.execute("INSERT OR REPLACE INTO propgroups(type,name,json) VALUES(?,?,?)",
                              (t, g, json.dumps({"name": g, "label": label, "displayOrder": -1, "archived": False})))
        for t, lst in schema.default_pipelines().items():
            for pl in lst:
                pl = dict(pl, createdAt=ts, updatedAt=ts, archived=False)
                for s in pl["stages"]:
                    s.update(createdAt=ts, updatedAt=ts, archived=False)
                wconn.execute("INSERT OR REPLACE INTO pipelines(type,id,json) VALUES(?,?,?)", (t, pl["id"], json.dumps(pl)))
        wconn.execute("COMMIT")
    invalidate_defs()
    _pl_cache.clear()


def reset():
    with W:
        wconn.execute("BEGIN IMMEDIATE")
        for tb in ("objects", "assoc", "uniq", "propdefs", "propgroups", "pipelines", "lists", "list_members", "hooks", "owners", "labels", "jobs"):
            wconn.execute(f"DELETE FROM {tb}")
        wconn.execute("DELETE FROM meta WHERE k!='seq'")
        wconn.execute("COMMIT")
        invalidate_defs()
        _pl_cache.clear()
        seed()


def meta_get(k, default=None):
    r = rconn().execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
    return r[0] if r else default


def meta_set(k, v):
    with W:
        wconn.execute("INSERT OR REPLACE INTO meta(k,v) VALUES(?,?)", (k, v))

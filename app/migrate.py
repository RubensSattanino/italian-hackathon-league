"""Sinergia 4 -> CRM migration (R1-R9)."""
import csv
import io
import json
import os
import re
import tempfile
import time
import unicodedata
import urllib.request
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta

from . import store, schema

FX = {"EUR": 1.0, "USD": 0.92, "GBP": 1.17}
DEL_TRUE = {"s", "si", "sì", "1", "y", "yes", "true", "x", "vero"}
EMAIL_RE = re.compile(r"^[a-z0-9._%+\-']+@[a-z0-9\-]+(\.[a-z0-9\-]+)*\.[a-z]{2,}$")

LOG = []


def log(*a):
    msg = " ".join(str(x) for x in a)
    LOG.append(msg)
    print("[migrate]", msg, flush=True)


# ------------------------------------------------------------------ helpers
def clean(s):
    if s is None:
        return ""
    return str(s).strip()


def is_deleted(v):
    return clean(v).lower() in DEL_TRUE


def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def parse_dt(s):
    """Parse the many Sinergia date shapes -> naive datetime or None."""
    s = clean(s)
    if not s:
        return None
    if re.fullmatch(r"\d{5}(\.\d+)?", s):  # Excel serial
        return datetime(1899, 12, 30) + timedelta(days=float(s))
    if re.fullmatch(r"\d{12,13}", s):
        return datetime.utcfromtimestamp(int(s) / 1000)
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?)?Z?", s)
    if m:
        y, mo, d, hh, mi, ss = m.groups()
        return _mk(int(y), int(mo), int(d), hh, mi, ss)
    m = re.fullmatch(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2}|\d{4})(?:[ T](\d{1,2})[:.](\d{2})(?:[:.](\d{2}))?)?", s)
    if m:
        d, mo, y, hh, mi, ss = m.groups()
        y = int(y)
        if y < 100:
            y += 2000 if y < 70 else 1900
        d, mo = int(d), int(mo)
        if mo > 12 and d <= 12:
            d, mo = mo, d
        return _mk(y, mo, d, hh, mi, ss)
    return None


def _mk(y, mo, d, hh, mi, ss):
    try:
        return datetime(y, mo, d, int(hh or 0), int(mi or 0), int(ss or 0))
    except ValueError:
        return None


def iso(dt):
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def date_iso(dt):
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%dT00:00:00.000Z")


def parse_number(s):
    """Parse an Italian/English formatted number string (no currency) -> float or None."""
    s = clean(s)
    if not s:
        return None
    s = s.replace(" ", "").replace(" ", "").replace("'", "")
    if not re.search(r"\d", s):
        return None
    s = re.sub(r"[^\d.,]", "", s)
    if not s:
        return None
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        if s.count(",") > 1:
            s = s.replace(",", "")
        else:
            s = s.replace(",", ".")
    elif "." in s:
        if s.count(".") > 1:
            s = s.replace(".", "")
        else:
            intp, dec = s.split(".")
            if len(dec) == 3 and len(intp) >= 1 and intp != "0":
                # ambiguous: treat 3 decimals as thousands separator
                s = intp + dec
    try:
        return float(s)
    except ValueError:
        return None


CUR_WORDS = [("eur", "EUR"), ("euro", "EUR"), ("€", "EUR"), ("usd", "USD"), ("$", "USD"), ("dollari", "USD"),
             ("gbp", "GBP"), ("£", "GBP"), ("sterline", "GBP")]


def norm_currency(s):
    s = clean(s).lower()
    if not s:
        return None
    for w, c in (("usd", "USD"), ("$", "USD"), ("dollar", "USD"), ("gbp", "GBP"), ("£", "GBP"), ("sterlin", "GBP"), ("pound", "GBP"),
                 ("eur", "EUR"), ("€", "EUR")):
        if w in s:
            return c
    return None


def parse_amount(raw):
    """-> (amount float|None, currency|None). Handles signs, (x), k/mila/mln, monthly (x12)."""
    s = clean(raw)
    if not s:
        return None, None
    low = s.lower()
    cur = norm_currency(re.sub(r"[\d.,\s\-()]", " ", low))
    neg = False
    if re.search(r"^\s*\(.*\)\s*$", s) or re.search(r"\(\s*[\d.,]+\s*\)", s):
        neg = True
    if re.search(r"-\s*[\d]", s) or re.search(r"[\d]\s*-\s*$", s) or re.search(r"^\s*[^\d]*-", s):
        neg = True
    mult = 1.0
    if re.search(r"\d\s*(k|mila)\b", low) or re.search(r"\d\s*k$", low):
        mult = 1000.0
    if re.search(r"(mln|milion|mio\b|\bm\b)", low):
        mult = 1_000_000.0
    monthly = bool(re.search(r"(/\s*mese|al\s*mese|mensil|mese)", low))
    m = re.search(r"\d[\d.,\s]*", s)
    if not m:
        return None, cur
    num = parse_number(m.group(0).strip())
    if num is None:
        return None, cur
    v = num * mult
    if monthly:
        v *= 12
    if neg:
        v = -v
    return round(v, 2), cur


def parse_discount(s):
    s = clean(s)
    if not s:
        return 0.0
    pct = "%" in s
    v = parse_number(s)
    if v is None:
        return 0.0
    if not pct and 0 < v < 1:
        v *= 100
    return round(v, 4)


def parse_qty(s):
    s = clean(s)
    if not s:
        return None
    m = re.search(r"\d[\d.,]*", s)
    if not m:
        return None
    return parse_number(m.group(0))


def norm_sku(s):
    d = re.sub(r"\D", "", clean(s))
    if not d:
        return None
    return "BF-" + d.zfill(5)


def clean_domain(s):
    s = clean(s).lower()
    if not s or s in ("-", "n.d.", "nd"):
        return None
    s = re.sub(r"^[a-z]+://", "", s)
    s = s.split("/")[0].split("?")[0].split("#")[0].split(":")[0]
    if "@" in s:
        s = s.split("@")[-1]
    if s.startswith("www."):
        s = s[4:]
    s = s.strip(". ")
    if "." not in s or " " in s:
        return None
    return s


PIVA_RE = re.compile(r"(?:p\.?\s*i\.?\s*v\.?\s*a\.?|partita\s*iva|vat|\bp\.?\s*i\.?(?=\s*[:.]?\s*(?:it)?\s*\d))\s*[:.\-n°]*\s*((?:it)?\s*[\d][\d\s.\-]{9,16}\d)", re.I)


def extract_piva(note):
    note = clean(note)
    if not note:
        return None
    m = PIVA_RE.search(note)
    if m:
        d = re.sub(r"\D", "", m.group(1))
        if len(d) == 11:
            return d
        if len(d) > 11:
            return d[:11]
    m = re.search(r"\bIT\s?(\d{11})\b", note)
    if m:
        return m.group(1)
    return None


def norm_email(s):
    e = clean(s).lower()
    e = e.replace("mailto:", "")
    e = re.sub(r"\s*[\(\[]\s*at\s*[\)\]]\s*", "@", e)
    e = re.sub(r"\s+", "", e).strip("<>\"';,")
    if EMAIL_RE.match(e):
        return e
    m = re.search(r"[a-z0-9._%+\-']+@[a-z0-9\-]+(\.[a-z0-9\-]+)*\.[a-z]{2,}", e)
    if m and EMAIL_RE.match(m.group(0)):
        return m.group(0)
    return None


def phone_key(s):
    raw = clean(s)
    d = re.sub(r"\D", "", raw)
    if raw.startswith("+39") and d.startswith("39"):
        d = d[2:]
    elif d.startswith("0039"):
        d = d[4:]
    return d if len(d) >= 6 else None


def ts_key(s):
    dt = parse_dt(s)
    return dt or datetime.min


def fmt2(v):
    return "%.2f" % v


def num_str(v):
    if v is None:
        return None
    if float(v).is_integer():
        return str(int(v))
    return ("%.6f" % v).rstrip("0").rstrip(".")


# ------------------------------------------------------------------ reading
def read_zip(path):
    files = {}
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            if n.endswith("/") or not n.lower().endswith(".csv"):
                continue
            base = os.path.basename(n).lower()
            raw = z.read(n)
            try:
                text = raw.decode("utf-8")
                if "�" in text:
                    raise UnicodeDecodeError("x", b"", 0, 1, "x")
            except UnicodeDecodeError:
                text = raw.decode("cp1252", errors="replace")
            text = text.lstrip("﻿")
            files[base] = list(csv.DictReader(io.StringIO(text, newline=""), delimiter=";"))
    return files


def pick(files, *names):
    for n in names:
        for k in files:
            if k.startswith(n):
                return files[k]
    return []


def migrate_from_url(url):
    t0 = time.time()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    req = urllib.request.Request(url, headers={"User-Agent": "crm-migrator/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            tmp.write(chunk)
    tmp.close()
    log("downloaded", os.path.getsize(tmp.name), "bytes in", round(time.time() - t0, 1), "s")
    try:
        migrate_file(tmp.name)
    finally:
        os.unlink(tmp.name)
    log("total", round(time.time() - t0, 1), "s")


def migrate_file(path):
    t0 = time.time()
    files = read_zip(path)
    log("parsed csv in", round(time.time() - t0, 1), "s", {k: len(v) for k, v in files.items()})
    M = Migration(files)
    M.run()


# ------------------------------------------------------------------ migration
class Migration:
    def __init__(self, files):
        self.f = files
        self.objects = []  # (id, type, props)
        self.assocs = []   # (from_id, to_id, from_type, to_type, type_id)
        self.next = None

    def nid(self):
        v = self.next
        self.next += 1
        return v

    def add(self, t, props):
        oid = self.nid()
        props = {k: v for k, v in props.items() if v is not None and v != ""}
        self.objects.append([oid, t, props])
        self.last_props = props
        return oid

    def link(self, f_t, f_id, t_t, t_id, primary=False):
        d = schema.default_assoc_type(f_t, t_t)
        rd = schema.default_assoc_type(t_t, f_t)
        self.assocs.append((f_id, t_id, f_t, t_t, d))
        self.assocs.append((t_id, f_id, t_t, f_t, rd))
        if primary:
            p = schema.ASSOC[(f_t, t_t)][1][0]
            rp = schema.ASSOC[(t_t, f_t)][1][0]
            self.assocs.append((f_id, t_id, f_t, t_t, p))
            self.assocs.append((t_id, f_id, t_t, f_t, rp))

    # -------------------------------------------------------------- users
    def users(self):
        rows = pick(self.f, "utenti", "users")
        self.U = {}
        for r in rows:
            uid = clean(r.get("id_utente")).upper()
            if not uid:
                continue
            self.U[uid] = {"id": uid, "first": clean(r.get("nome")), "last": clean(r.get("cognome")),
                           "email": clean(r.get("email")).lower(), "manager": clean(r.get("responsabile")).upper(),
                           "active": clean(r.get("attivo")).lower() in DEL_TRUE, "role": clean(r.get("ruolo"))}
        self.owner_ids = {}
        for i, (uid, u) in enumerate(sorted(self.U.items())):
            self.owner_ids[uid] = str(10000 + i + 1)

    def _nk(self, s):
        s = strip_accents(clean(s)).lower()
        return re.sub(r"[^a-z]", "", s)

    def resolve_user_ref(self, ref):
        """Text in a Sinergia user column -> user id or None."""
        r = clean(ref)
        if not r:
            return None
        ru = r.upper()
        if ru in self.U:
            return ru
        m = re.fullmatch(r"U?\s*0*(\d+)", ru)
        if m:
            k = "U%02d" % int(m.group(1))
            if k in self.U:
                return k
        if "@" in r:
            for uid, u in self.U.items():
                if u["email"] == r.lower():
                    return uid
        toks = [self._nk(t) for t in re.split(r"[\s,]+", strip_accents(r)) if self._nk(t)]
        cands = []
        for uid, u in self.U.items():
            f, l = self._nk(u["first"]), self._nk(u["last"])
            full = self._nk(r)
            if full in (f + l, l + f):
                cands.append(uid)
                continue
            # initial + last name, e.g. "Mazza E." / "T. Lombardo"
            if len(toks) >= 2:
                initials = [t for t in toks if len(t) == 1]
                rest = "".join(t for t in toks if len(t) > 1)
                if initials and rest == l and initials[0] == f[:1]:
                    cands.append(uid)
        if not cands:
            return None
        cands.sort(key=lambda u: (not self.U[u]["active"], u))
        return cands[0]

    def effective_user(self, uid):
        """Who follows it today: active self, else the same person's active account, else manager chain."""
        seen = set()
        while uid and uid in self.U and uid not in seen:
            seen.add(uid)
            u = self.U[uid]
            if u["active"]:
                return uid
            twin = [k for k, v in self.U.items() if v["active"] and self._nk(v["first"]) == self._nk(u["first"]) and self._nk(v["last"]) == self._nk(u["last"])]
            if twin:
                return sorted(twin)[0]
            uid = u["manager"]
        return None

    # -------------------------------------------------------------- run
    def run(self):
        t0 = time.time()
        store.reset()
        self.next = store.next_id(5_000_000)  # reserve a big block
        self.users()
        self.setup_schema()
        self.companies()
        self.contacts()
        self.products()
        self.deals()
        self.line_items()
        self.tickets()
        self.activities()
        self.f.clear()
        import gc; gc.collect()
        self.figures()
        log("built", len(self.objects), "objects,", len(self.assocs), "assoc rows in", round(time.time() - t0, 1), "s")
        self.write()
        log("written in", round(time.time() - t0, 1), "s")

    # -------------------------------------------------------------- schema
    def setup_schema(self):
        now = store.now_iso()

        def prop(t, name, label, typ="string", field="text", unique=False, options=None):
            store.save_propdef(t, {"name": name, "label": label, "type": typ, "fieldType": field, "groupName": "information",
                                   "description": "Migrated from Sinergia 4", "options": options or [], "hasUniqueValue": unique,
                                   "hidden": False, "formField": True, "displayOrder": -1, "calculated": False, "externalOptions": False,
                                   "createdAt": now, "updatedAt": now, "archived": False})
        for t in ("companies", "contacts", "deals", "line_items", "tickets", "notes", "calls", "emails", "meetings"):
            prop(t, "id_legacy", "ID Sinergia")
        prop("deals", "commerciale", "Commerciale")
        prop("tickets", "assegnatario", "Assegnatario")
        for t in ("notes", "calls", "emails", "meetings"):
            prop(t, "autore", "Autore")
        prop("companies", "partita_iva", "Partita IVA", unique=True)
        prop("companies", "fatturato_2025", "Fatturato 2025", "number", "number")
        prop("companies", "classe_cliente", "Classe cliente", "string", "text")
        # pipelines
        def stage(label, order, prob=None, closed=False, ticket=False):
            sid = str(store.next_id())
            md = {"isClosed": "true" if closed else "false"}
            if ticket:
                md["ticketState"] = "CLOSED" if closed else "OPEN"
            else:
                md["probability"] = str(prob)
            return {"id": sid, "label": label, "displayOrder": order, "metadata": md, "createdAt": now, "updatedAt": now, "archived": False}
        ren = {"id": str(store.next_id()), "label": "Rinnovi", "displayOrder": 1, "createdAt": now, "updatedAt": now, "archived": False,
               "stages": [stage("Da rinnovare", 0, 0.2), stage("In trattativa", 1, 0.6), stage("Rinnovato", 2, 1.0, True), stage("Non rinnovato", 3, 0.0, True)]}
        store.pipeline_save("deals", ren)
        ass = {"id": str(store.next_id()), "label": "Assistenza", "displayOrder": 1, "createdAt": now, "updatedAt": now, "archived": False,
               "stages": [stage("Aperto", 0, ticket=True), stage("In lavorazione", 1, ticket=True),
                          stage("In attesa del cliente", 2, ticket=True), stage("Chiuso", 3, closed=True, ticket=True)]}
        store.pipeline_save("tickets", ass)
        self.ren = ren
        self.ren_stage = {s["label"]: s["id"] for s in ren["stages"]}
        self.ass = ass
        self.ass_stage = {s["label"]: s["id"] for s in ass["stages"]}
        # owners
        with store.W:
            for uid, u in self.U.items():
                oid = self.owner_ids[uid]
                o = {"id": oid, "email": u["email"], "firstName": u["first"], "lastName": u["last"], "userId": int(oid),
                     "userIdIncludingInactive": int(oid), "createdAt": now, "updatedAt": now, "archived": not u["active"], "teams": [],
                     "type": "PERSON"}
                store.wconn.execute("INSERT OR REPLACE INTO owners(id,email,json) VALUES(?,?,?)", (int(oid), u["email"], json.dumps(o, ensure_ascii=False)))

    # -------------------------------------------------------------- companies (R1, R7)
    def companies(self):
        rows = [r for r in pick(self.f, "aziende", "companies") if not is_deleted(r.get("cancellato")) and clean(r.get("id_azienda"))]
        parent = {}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb
        by_key = {}
        info = {}
        for r in rows:
            rid = clean(r["id_azienda"])
            parent[rid] = rid
            dom = clean_domain(r.get("sito_web"))
            piva = extract_piva(r.get("note"))
            info[rid] = (r, dom, piva)
            for k in (("d", dom), ("p", piva)):
                if k[1]:
                    if k in by_key:
                        union(rid, by_key[k])
                    else:
                        by_key[k] = rid
        groups = defaultdict(list)
        for rid in info:
            groups[find(rid)].append(rid)
        self.company_map = {}   # legacy id -> new id
        self.company_props = {}
        self.domain_to_company = {}
        merged = 0
        for g in groups.values():
            g.sort(key=lambda x: ts_key(info[x][0].get("ultima_modifica")), reverse=True)  # most recent first
            if len(g) > 1:
                merged += len(g) - 1
            rows_g = [info[x][0] for x in g]

            def first(col):
                for rr in rows_g:
                    v = clean(rr.get(col))
                    if v:
                        return v
                return None
            doms = []
            for x in g:
                d = info[x][1]
                if d and d not in doms:
                    doms.append(d)
            piva = next((info[x][2] for x in g if info[x][2]), None)
            prov = first("provincia")
            props = {"id_legacy": g[0], "name": first("ragione_sociale"), "domain": doms[0] if doms else None,
                     "hs_additional_domains": ";".join(doms[1:]) if len(doms) > 1 else None,
                     "city": first("citta"), "state": prov.upper() if prov else None, "partita_iva": piva,
                     "description": first("note")}
            nid = self.add("companies", props)
            self.company_props[nid] = self.last_props
            for x in g:
                self.company_map[x] = nid
            for d in doms:
                self.domain_to_company.setdefault(d, nid)
        log("companies", len(rows), "->", len(groups), "(merged", merged, ")")

    # -------------------------------------------------------------- contacts (R2, R12)
    LIFECYCLE = {"lead": "lead", "prospect": "opportunity", "cliente": "customer", "excliente": "other", "ex": "other"}

    def lifecycle(self, s):
        k = re.sub(r"[^a-z]", "", strip_accents(clean(s)).lower())
        if not k:
            return None
        if k.startswith("ex"):
            return "other"
        if "prospect" in k:
            return "opportunity"
        if "cliente" in k or "customer" in k:
            return "customer"
        if "lead" in k:
            return "lead"
        return None

    def contacts(self):
        rows = [r for r in pick(self.f, "contatti", "contacts") if not is_deleted(r.get("cancellato")) and clean(r.get("id_contatto"))]
        swapped = 0
        for r in rows:
            em, ph = clean(r.get("email")), clean(r.get("telefono"))
            if "@" not in em and "(at)" not in em.lower() and ("@" in ph or "(at)" in ph.lower()):
                r["email"], r["telefono"] = ph, em
                swapped += 1
            r["_email"] = norm_email(r.get("email"))
        # union-find: same valid email, or same first+last+phone when emails do not conflict
        parent = {i: i for i in range(len(rows))}
        emails = {i: ({rows[i]["_email"]} if rows[i]["_email"] else set()) for i in range(len(rows))}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b, strict):
            ra, rb = find(a), find(b)
            if ra == rb:
                return
            if strict and len(emails[ra] | emails[rb]) > 1:
                return
            parent[ra] = rb
            emails[rb] |= emails.pop(ra)
        by_email = {}
        for i, r in enumerate(rows):
            if r["_email"]:
                if r["_email"] in by_email:
                    union(i, by_email[r["_email"]], False)
                else:
                    by_email[r["_email"]] = i
        by_np = {}
        for i, r in enumerate(rows):
            pk = phone_key(r.get("telefono"))
            if not pk:
                continue
            k = (strip_accents(clean(r.get("nome"))).lower(), strip_accents(clean(r.get("cognome"))).lower(), pk)
            if k in by_np:
                union(i, by_np[k], True)
            else:
                by_np[k] = i
        gmap = defaultdict(list)
        for i in range(len(rows)):
            gmap[find(i)].append(rows[i])
        groups = {}
        singles = list(gmap.values())
        log("contacts swapped email/phone", swapped)
        self.contact_map = {}
        self.contact_company = {}
        self.email_to_contact = {}
        auto = 0
        for g in list(groups.values()) + singles:
            g.sort(key=lambda r: ts_key(r.get("ultima_modifica")), reverse=True)

            def first(col):
                for rr in g:
                    v = clean(rr.get(col))
                    if v:
                        return v
                return None
            comp = None
            for rr in g:
                c = self.company_map.get(clean(rr.get("id_azienda")))
                if c:
                    comp = c
                    break
            lc = None
            for rr in g:
                lc = self.lifecycle(rr.get("tipo"))
                if lc:
                    break
            email = next((rr["_email"] for rr in g if rr["_email"]), None)
            props = {"id_legacy": clean(g[0]["id_contatto"]), "firstname": first("nome"), "lastname": first("cognome"),
                     "email": email, "phone": first("telefono"), "lifecyclestage": lc}
            if comp is None and email:
                dom = email.split("@")[1]
                comp = self.domain_to_company.get(dom)
                if comp:
                    auto += 1
            if comp:
                props["associatedcompanyid"] = None  # set after id known
            nid = self.add("contacts", props)
            if comp:
                self.objects[-1][2]["associatedcompanyid"] = str(comp)
                self.link("contacts", nid, "companies", comp, primary=True)
                self.contact_company[nid] = comp
            for rr in g:
                self.contact_map[clean(rr["id_contatto"])] = nid
            if email:
                self.email_to_contact[email] = nid
        log("contacts", len(rows), "->", len(groups) + len(singles), "auto-company", auto)

    # -------------------------------------------------------------- products (R4)
    def products(self):
        rows = [r for r in pick(self.f, "listino", "products") if not is_deleted(r.get("cancellato"))]
        by = defaultdict(list)
        for r in rows:
            sku = norm_sku(r.get("codice_articolo"))
            if sku:
                by[sku].append(r)
        self.product = {}
        for sku, g in by.items():
            g.sort(key=lambda r: ts_key(r.get("ultima_modifica")), reverse=True)
            name = next((clean(r.get("descrizione")) for r in g if clean(r.get("descrizione"))), None)
            price = next((parse_number(r.get("prezzo_listino")) for r in g if parse_number(r.get("prezzo_listino")) is not None), None)
            unit = next((clean(r.get("unita")) for r in g if clean(r.get("unita"))), None)
            props = {"hs_sku": sku, "name": name, "price": num_str(round(price, 2)) if price is not None else None,
                     "description": name}
            nid = self.add("products", props)
            self.product[sku] = (nid, name, price)
        log("products", len(rows), "->", len(by))

    # -------------------------------------------------------------- deals (R3)
    SALES = [("contatto", "appointmentscheduled"), ("qualifica", "qualifiedtobuy"), ("presentazione", "presentationscheduled"),
             ("decisione", "decisionmakerboughtin"), ("contratto", "contractsent"), ("vinta", "closedwon"), ("persa", "closedlost")]
    SALES_CODE = {"01": "appointmentscheduled", "02": "qualifiedtobuy", "03": "presentationscheduled", "04": "decisionmakerboughtin",
                  "05": "contractsent", "06": "closedwon", "07": "closedlost"}
    REN = [("non rinnovato", "Non rinnovato"), ("rinnovato", "Rinnovato"), ("in trattativa", "In trattativa"), ("trattativa", "In trattativa"),
           ("da rinnovare", "Da rinnovare")]
    REN_CODE = {"R1": "Da rinnovare", "R2": "In trattativa", "R3": "Rinnovato", "R4": "Non rinnovato"}

    def stage_of(self, fase):
        """-> ('sales', stageid) | ('ren', label) | (None, None)"""
        f = strip_accents(clean(fase)).lower()
        if not f:
            return None, None
        m = re.match(r"^r\s*0?([1-4])\b", f)
        if m:
            return "ren", self.REN_CODE["R" + m.group(1)]
        for k, v in self.REN:
            if k in f:
                return "ren", v
        m = re.match(r"^0?([1-7])\b", f)
        if m:
            return "sales", self.SALES_CODE["0" + m.group(1)]
        for k, v in self.SALES:
            if k in f:
                return "sales", v
        return None, None

    def deals(self):
        rows = [r for r in pick(self.f, "opportunita", "deals") if not is_deleted(r.get("cancellato")) and clean(r.get("id_opportunita"))]
        hist = defaultdict(list)
        for h in pick(self.f, "storico_fasi", "storico"):
            hist[clean(h.get("id_opportunita"))].append(h)
        # live line totals per deal
        self.righe = defaultdict(list)
        for r in pick(self.f, "righe_offerta", "righe"):
            if is_deleted(r.get("cancellato")):
                continue
            self.righe[clean(r.get("id_opportunita"))].append(r)
        self.deal_map = {}
        self.deal_info = {}
        mism = 0
        for r in rows:
            lid = clean(r["id_opportunita"])
            pl_raw = strip_accents(clean(r.get("pipeline"))).lower()
            kind, st = self.stage_of(r.get("fase"))
            if "rinnov" in pl_raw:
                pipeline = "ren"
            elif "vend" in pl_raw:
                pipeline = "sales"
            else:
                pipeline = kind or "sales"
            if kind and kind != pipeline:
                mism += 1
                if pipeline == "ren":
                    st = {"closedwon": "Rinnovato", "closedlost": "Non rinnovato"}.get(st, "Da rinnovare" if st in ("appointmentscheduled", "qualifiedtobuy") else "In trattativa")
                else:
                    st = {"Rinnovato": "closedwon", "Non rinnovato": "closedlost", "Da rinnovare": "appointmentscheduled", "In trattativa": "decisionmakerboughtin"}[st]
            if st is None:
                # take last stage from history
                hs = sorted(hist.get(lid, []), key=lambda h: ts_key(h.get("data_cambio")))
                if hs:
                    k2, s2 = self.stage_of(hs[-1].get("fase_nuova"))
                    if k2 == pipeline:
                        st = s2
            if st is None:
                st = "appointmentscheduled" if pipeline == "sales" else "Da rinnovare"
            if pipeline == "ren":
                pipe_id, stage_id = self.ren["id"], self.ren_stage[st]
                won, lost = st == "Rinnovato", st == "Non rinnovato"
            else:
                pipe_id, stage_id = "default", st
                won, lost = st == "closedwon", st == "closedlost"
            close = parse_dt(r.get("data_chiusura"))
            if close is None and (won or lost):
                for h in sorted(hist.get(lid, []), key=lambda h: ts_key(h.get("data_cambio")), reverse=True):
                    k2, s2 = self.stage_of(h.get("fase_nuova"))
                    if s2 == st or (pipeline == "ren" and s2 == st):
                        close = parse_dt(h.get("data_cambio"))
                        break
            amount, cur = parse_amount(r.get("importo"))
            vcur = norm_currency(r.get("valuta"))
            currency = vcur or cur or "EUR"
            lines = self.righe.get(lid)
            if lines:
                tot = 0.0
                for ln in lines:
                    tot += self.line_total(ln)[3]
                amount = round(tot, 2)
                currency = "EUR"
            if amount is None:
                currency = None
            uid = self.resolve_user_ref(r.get("id_commerciale"))
            eff = self.effective_user(uid) if uid else None
            props = {"id_legacy": lid, "dealname": clean(r.get("titolo")), "amount": num_str(amount) if amount is not None else None,
                     "deal_currency_code": currency, "pipeline": pipe_id, "dealstage": stage_id,
                     "closedate": date_iso(close), "commerciale": self.U[eff]["email"] if eff else None,
                     "hubspot_owner_id": self.owner_ids.get(eff) if eff else None,
                     "hs_is_closed": "true" if (won or lost) else "false", "hs_is_closed_won": "true" if won else "false"}
            nid = self.add("deals", props)
            self.deal_map[lid] = nid
            comp = self.company_map.get(clean(r.get("id_azienda")))
            if comp:
                self.link("deals", nid, "companies", comp, primary=True)
            seen = set()
            for c in re.split(r"[;,|\s/]+", clean(r.get("contatti"))):
                c = clean(c)
                if not c:
                    continue
                cid = self.contact_map.get(c)
                if cid and cid not in seen:
                    seen.add(cid)
                    self.link("deals", nid, "contacts", cid)
            amt_eur = (amount or 0) * FX.get(currency or "EUR", 1.0)
            self.deal_info[nid] = {"won": won, "close": close, "amount_eur": amt_eur, "company": comp, "contacts": seen, "owner": eff}
        log("deals", len(rows), "pipeline/stage mismatches", mism)

    def line_total(self, ln):
        sku = norm_sku(ln.get("codice_articolo"))
        prod = self.product.get(sku) if sku else None
        q = parse_qty(ln.get("quantita"))
        if q is None:
            q = 1.0
        p, _ = parse_amount(ln.get("prezzo_unitario"))
        if p is None and prod:
            p = prod[2]
        if p is None:
            p = 0.0
        p = abs(p)
        d = parse_discount(ln.get("sconto"))
        total = round(q * p * (1 - d / 100.0) + 1e-9, 2)
        return q, p, d, total

    def line_items(self):
        n = 0
        for lid, lines in self.righe.items():
            deal = self.deal_map.get(lid)
            if not deal:
                continue
            for ln in lines:
                q, p, d, total = self.line_total(ln)
                sku = norm_sku(ln.get("codice_articolo"))
                prod = self.product.get(sku) if sku else None
                name = clean(ln.get("descrizione")) or (prod[1] if prod else None)
                props = {"id_legacy": clean(ln.get("id_riga")), "name": name, "quantity": num_str(q), "price": num_str(round(p, 2)),
                         "hs_discount_percentage": num_str(d), "amount": num_str(total), "hs_sku": sku if prod else (sku or None),
                         "hs_product_id": str(prod[0]) if prod else None, "hs_line_item_currency_code": "EUR"}
                nid = self.add("line_items", props)
                self.link("line_items", nid, "deals", deal)
                n += 1
        log("line_items", n)

    # -------------------------------------------------------------- tickets (R5)
    def ticket_stage(self, s):
        k = strip_accents(clean(s)).lower()
        if "chius" in k or "risolt" in k or "closed" in k:
            return "Chiuso"
        if "attesa" in k:
            return "In attesa del cliente"
        if "lavoraz" in k or "corso" in k:
            return "In lavorazione"
        return "Aperto"

    def priority(self, s):
        k = strip_accents(clean(s)).lower()
        if not k:
            return None
        if "urg" in k or k.startswith("4"):
            return "URGENT"
        if "alt" in k or k.startswith("3"):
            return "HIGH"
        if "bass" in k or k.startswith("1"):
            return "LOW"
        if "med" in k or "norm" in k or k.startswith("2"):
            return "MEDIUM"
        return None

    def tickets(self):
        rows = [r for r in pick(self.f, "ticket", "tickets") if not is_deleted(r.get("cancellato")) and clean(r.get("id_ticket"))]
        from_hdr = 0
        for r in rows:
            st = self.ticket_stage(r.get("stato"))
            opened = parse_dt(r.get("aperto_il"))
            closed = parse_dt(r.get("chiuso_il"))
            uid = self.resolve_user_ref(r.get("id_utente"))
            eff = self.effective_user(uid) if uid else None
            props = {"id_legacy": clean(r["id_ticket"]), "subject": clean(r.get("oggetto")), "content": clean(r.get("descrizione")),
                     "hs_pipeline": self.ass["id"], "hs_pipeline_stage": self.ass_stage[st], "hs_ticket_priority": self.priority(r.get("priorita")),
                     "createdate": iso(opened), "closed_date": iso(closed) if closed else None,
                     "assegnatario": self.U[eff]["email"] if eff else None, "hubspot_owner_id": self.owner_ids.get(eff) if eff else None}
            nid = self.add("tickets", props)
            if opened:
                self.objects[-1].append(iso(opened))
            cid = self.contact_map.get(clean(r.get("id_contatto")))
            if not cid:
                m = re.match(r"\s*(?:da|from)\s*:\s*(\S+@\S+)", clean(r.get("descrizione")), re.I)
                if m:
                    e = norm_email(m.group(1))
                    cid = self.email_to_contact.get(e) if e else None
                    if cid:
                        from_hdr += 1
            if cid:
                self.link("tickets", nid, "contacts", cid)
            comp = self.company_map.get(clean(r.get("id_azienda")))
            if comp:
                self.link("tickets", nid, "companies", comp, primary=True)
        log("tickets", len(rows), "contact from header", from_hdr)

    # -------------------------------------------------------------- activities (R6)
    def act_type(self, s):
        k = strip_accents(clean(s)).lower()
        if any(w in k for w in ("tel", "chiam", "call")):
            return "calls"
        if "mail" in k:
            return "emails"
        if any(w in k for w in ("meet", "riun", "incontr", "visit")):
            return "meetings"
        return "notes"

    def activities(self):
        rows = pick(self.f, "attivita", "activities")
        body = {"notes": "hs_note_body", "calls": "hs_call_body", "emails": "hs_email_text", "meetings": "hs_meeting_body"}
        seen = set()
        self.act_year = defaultdict(set)  # contact/deal id -> set(years)
        n = dup = 0
        for r in rows:
            if is_deleted(r.get("cancellato")) or not clean(r.get("id_attivita")):
                continue
            t = self.act_type(r.get("tipo"))
            dt = parse_dt(r.get("data"))
            text = clean(r.get("testo"))
            cid = self.contact_map.get(clean(r.get("id_contatto")))
            did = self.deal_map.get(clean(r.get("id_opportunita")))
            key = (t, dt, text, cid, did)
            if key in seen:
                dup += 1
                continue
            seen.add(key)
            uid = self.resolve_user_ref(r.get("id_utente"))
            props = {"id_legacy": clean(r["id_attivita"]), "hs_timestamp": iso(dt), body[t]: text,
                     "autore": self.U[uid]["email"] if uid else None}
            if dt:
                props["createdate"] = iso(dt)
            if t == "meetings" and dt:
                props["hs_meeting_start_time"] = iso(dt)
                props["hs_meeting_end_time"] = iso(dt + timedelta(hours=1))
                props["hs_meeting_title"] = text.split("\n")[0][:80]
            if t == "calls":
                props["hs_call_title"] = text.split("\n")[0][:80]
                props["hs_call_status"] = "COMPLETED"
            if t == "emails":
                props["hs_email_subject"] = text.split("\n")[0][:80]
                props["hs_email_direction"] = "EMAIL"
            if uid and self.owner_ids.get(uid):
                props["hubspot_owner_id"] = self.owner_ids[uid]
            nid = self.add(t, props)
            if dt:
                self.objects[-1].append(iso(dt))
            if cid:
                self.link(t, nid, "contacts", cid)
                if dt:
                    self.act_year[cid].add(dt.year)
            if did:
                self.link(t, nid, "deals", did)
                if dt:
                    self.act_year[did].add(dt.year)
            n += 1
        log("activities", n, "dups skipped", dup)

    # -------------------------------------------------------------- R8, R9
    def figures(self):
        rev = defaultdict(float)
        won_any = set()
        comp_deals = defaultdict(set)
        for did, inf in self.deal_info.items():
            c = inf["company"]
            if not c:
                continue
            comp_deals[c].add(did)
            if inf["won"]:
                won_any.add(c)
                if inf["close"] and inf["close"].year == 2025:
                    rev[c] += inf["amount_eur"]
        comp_contacts = defaultdict(set)
        for cid, comp in self.contact_company.items():
            comp_contacts[comp].add(cid)
        self.dormant = []
        for oid, props in self.company_props.items():
            v = round(rev.get(oid, 0.0) + 1e-9, 2)
            props["fatturato_2025"] = fmt2(v) if v != 0 else "0"
            props["classe_cliente"] = "A" if v >= 100000 else "B" if v >= 20000 else "C" if v > 0 else None
            if props["classe_cliente"] is None:
                props.pop("classe_cliente")
            if oid in won_any:
                active = any(2025 in self.act_year.get(x, ()) for x in comp_contacts.get(oid, ())) or \
                    any(2025 in self.act_year.get(x, ()) for x in comp_deals.get(oid, ()))
                if not active:
                    self.dormant.append(oid)
        log("R8 classes", {k: sum(1 for p in self.company_props.values() if p.get("classe_cliente") == k) for k in "ABC"}, "R9 dormant", len(self.dormant))

    # -------------------------------------------------------------- write
    def write(self):
        now = store.now_iso()
        c = store.wconn
        with store.W:
            c.execute("BEGIN IMMEDIATE")
            try:
                uniq = []

                def gen():
                    for o in self.objects:
                        oid, t, p = o[0], o[1], o[2]
                        created = p.get("createdate") or (o[3] if len(o) > 3 else now)
                        p["createdate"] = created
                        p["hs_lastmodifieddate"] = now
                        if t == "contacts":
                            p["lastmodifieddate"] = now
                            if p.get("email"):
                                uniq.append(("contacts", "email", p["email"], oid))
                        if t == "companies" and p.get("partita_iva"):
                            uniq.append(("companies", "partita_iva", p["partita_iva"], oid))
                        yield (oid, t, json.dumps(p, ensure_ascii=False), created, now)
                c.executemany("INSERT INTO objects(id,type,props,created,updated,archived) VALUES(?,?,?,?,?,0)", gen())
                c.executemany("INSERT OR IGNORE INTO uniq(type,prop,value,obj_id) VALUES(?,?,?,?)", uniq)
                c.executemany("INSERT OR IGNORE INTO assoc(from_id,to_id,from_type,to_type,type_id,category) VALUES(?,?,?,?,?,'HUBSPOT_DEFINED')", self.assocs)
                c.execute("COMMIT")
            except Exception:
                c.execute("ROLLBACK")
                raise
        from .api import create_list
        create_list("Clienti dormienti", "0-2", "MANUAL", None, self.dormant)
        store.meta_set("migrated_at", now)
        c.execute("PRAGMA optimize")

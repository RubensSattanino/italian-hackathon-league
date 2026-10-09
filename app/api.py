"""HTTP routes (HubSpot-compatible CRM API)."""
import csv
import io
import json
import os
import time
import uuid
from datetime import datetime, timezone

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, PlainTextResponse
from starlette.routing import Route

from . import store, schema
from .store import ApiError, not_found

TOKENS = [t for t in (os.environ.get("CRM_TOKEN"), os.environ.get("TOKEN"), os.environ.get("API_TOKEN")) if t]


def J(data, status=200):
    return Response(json.dumps(data, ensure_ascii=False), status_code=status, media_type="application/json")


def err(e: ApiError):
    return J(e.body(), e.status)


def handler(fn):
    async def wrapped(request: Request):
        body = None
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            raw = await request.body()
            if raw:
                try:
                    body = json.loads(raw)
                except Exception:
                    return err(ApiError(400, "Invalid input JSON on line 1: could not parse request body", "VALIDATION_ERROR"))
        try:
            res = await run_in_threadpool(fn, request, body)
        except ApiError as e:
            return err(e)
        except Exception as e:  # noqa
            import traceback
            traceback.print_exc()
            return err(ApiError(500, f"Internal error: {e}", "INTERNAL_ERROR"))
        if isinstance(res, Response):
            return res
        if res is None:
            return Response(status_code=204)
        if isinstance(res, tuple):
            return J(res[0], res[1])
        return J(res)
    wrapped.__name__ = fn.__name__
    return wrapped


def otype(request):
    t = schema.norm_type(request.path_params.get("type"))
    if not t:
        raise ApiError(404, f"Unable to infer object type from: {request.path_params.get('type')}", "OBJECT_NOT_FOUND")
    return t


def qlist(request, name):
    vals = request.query_params.getlist(name)
    out = []
    for v in vals:
        out.extend([x.strip() for x in v.split(",") if x.strip()])
    return out


def ts():
    return store.now_iso()


# ------------------------------------------------------------------ objects
@handler
def obj_list(request, body):
    t = otype(request)
    try:
        limit = int(request.query_params.get("limit", 10))
    except ValueError:
        raise ApiError(400, "limit must be an integer")
    limit = max(1, min(limit, 100))
    archived = request.query_params.get("archived", "false").lower() == "true"
    objs, nxt = store.list_objects(t, limit, request.query_params.get("after"), archived)
    props = qlist(request, "properties")
    assocs = qlist(request, "associations")
    res = {"results": [store.to_api(o, props or None, assocs) for o in objs]}
    if nxt:
        res["paging"] = {"next": {"after": nxt, "link": f"{request.url.path}?after={nxt}"}}
    return res


@handler
def obj_create(request, body):
    t = otype(request)
    body = body or {}
    o = store.create(t, body.get("properties") or {}, body.get("associations"))
    return store.to_api(o), 201


@handler
def obj_get(request, body):
    t = otype(request)
    oid = request.path_params["id"]
    idp = request.query_params.get("idProperty")
    archived = request.query_params.get("archived", "false").lower() == "true"
    if idp:
        o = store.find_by_prop(t, idp, oid)
    else:
        o = store.get_obj(t, oid, include_archived=archived)
    if not o:
        raise not_found("Object not found.  objectId are usually numeric.")
    return store.to_api(o, qlist(request, "properties") or None, qlist(request, "associations"))


@handler
def obj_update(request, body):
    t = otype(request)
    body = body or {}
    o = store.update(t, request.path_params["id"], body.get("properties") or {}, request.query_params.get("idProperty"))
    return store.to_api(o)


@handler
def obj_delete(request, body):
    t = otype(request)
    store.archive(t, request.path_params["id"])
    return None


@handler
def obj_search(request, body):
    t = otype(request)
    total, objs, nxt = store.search(t, body or {})
    props = (body or {}).get("properties") or None
    res = {"total": total, "results": [store.to_api(o, props) for o in objs]}
    if nxt:
        res["paging"] = {"next": {"after": nxt}}
    return res


@handler
def obj_merge(request, body):
    t = otype(request)
    body = body or {}
    o = store.merge(t, body.get("primaryObjectId"), body.get("objectIdToMerge"))
    return store.to_api(o)


def _batch_inputs(body):
    inputs = (body or {}).get("inputs")
    if inputs is None or not isinstance(inputs, list):
        raise ApiError(400, "Invalid input JSON: inputs is required", "VALIDATION_ERROR")
    if len(inputs) > 100:
        raise ApiError(400, "Batch size cannot exceed 100", "VALIDATION_ERROR")
    return inputs


def _batch_result(results, errors, started, status_ok=200):
    res = {"status": "COMPLETE", "results": results, "startedAt": started, "completedAt": ts()}
    if errors:
        res["errors"] = errors
        res["numErrors"] = len(errors)
        return res, 207
    return res, status_ok


@handler
def obj_batch(request, body):
    t = otype(request)
    action = request.path_params["action"]
    started = ts()
    inputs = _batch_inputs(body)
    results, errors = [], []
    if action == "read":
        idp = body.get("idProperty")
        props = body.get("properties") or None
        missing = []
        for inp in inputs:
            iid = inp.get("id")
            o = store.find_by_prop(t, idp, iid) if idp and idp != "hs_object_id" else store.get_obj(t, iid, include_archived=bool(body.get("archived")))
            if o:
                results.append(store.to_api(o, props))
            else:
                missing.append(str(iid))
        if missing:
            errors.append({"status": "error", "category": "OBJECT_NOT_FOUND",
                           "message": f"Could not get some {schema.SINGULAR_OF.get(t, t).upper()} objects, they may be deleted or not exist. Check that ids are valid.",
                           "context": {"ids": missing}})
        return _batch_result(results, errors, started)
    if action == "create":
        for inp in inputs:
            store.prepare_props(t, inp.get("properties") or {})
        for inp in inputs:
            try:
                results.append(store.to_api(store.create(t, inp.get("properties") or {}, inp.get("associations"))))
            except ApiError as e:
                if len(inputs) == 1:
                    raise
                errors.append(dict(e.body(), status="error"))
        if errors and not results:
            raise ApiError(errors[0].get("category") == "CONFLICT" and 409 or 400, errors[0]["message"], errors[0]["category"])
        return _batch_result(results, errors, started, 201)
    if action == "update":
        idp = body.get("idProperty")
        for inp in inputs:
            try:
                results.append(store.to_api(store.update(t, inp.get("id"), inp.get("properties") or {}, inp.get("idProperty") or idp)))
            except ApiError as e:
                if len(inputs) == 1:
                    raise
                errors.append(dict(e.body(), status="error", context={"ids": [str(inp.get("id"))]}))
        return _batch_result(results, errors, started)
    if action == "upsert":
        for inp in inputs:
            idp = inp.get("idProperty") or body.get("idProperty") or "hs_object_id"
            iid = inp.get("id")
            props = dict(inp.get("properties") or {})
            with store.W:
                o = store.find_by_prop(t, idp, iid, conn=store.wconn) if idp != "hs_object_id" else store.get_obj(t, iid, conn=store.wconn)
                if o:
                    o = store.update(t, o["id"], props)
                    r = store.to_api(o)
                    r["new"] = False
                else:
                    if idp != "hs_object_id":
                        props.setdefault(idp, iid)
                    o = store.create(t, props)
                    r = store.to_api(o)
                    r["new"] = True
            results.append(r)
        return _batch_result(results, errors, started)
    if action == "archive":
        for inp in inputs:
            store.archive(t, inp.get("id"))
        return None
    raise ApiError(404, "Unknown batch action", "OBJECT_NOT_FOUND")


# ------------------------------------------------------------------ associations
def _check_obj(t, oid):
    if not store.get_obj(t, oid):
        raise not_found(f"No {schema.SINGULAR_OF.get(t, t)} with ID {oid} exists")


def _v4_results(t, oid, to_t, limit=500, after=None):
    lst = store.get_assocs(oid, to_t)
    results = []
    for to_id, types in lst:
        results.append({"toObjectId": to_id, "associationTypes": [{"category": c, "typeId": tid, "label": label} for c, tid, label in types]})
    try:
        start = int(after or 0)
    except ValueError:
        start = 0
    page = results[start:start + limit]
    res = {"results": page}
    if start + limit < len(results):
        res["paging"] = {"next": {"after": str(start + limit)}}
    return res


@handler
def v4_assoc_list(request, body):
    t = otype(request)
    to_t = schema.norm_type(request.path_params["toType"])
    if not to_t:
        raise ApiError(400, "Unknown object type", "VALIDATION_ERROR")
    oid = request.path_params["id"]
    _check_obj(t, oid)
    limit = int(request.query_params.get("limit", 500))
    return _v4_results(t, oid, to_t, limit, request.query_params.get("after"))


@handler
def v4_assoc_default(request, body):
    t = otype(request)
    to_t = schema.norm_type(request.path_params["toType"])
    oid, toid = request.path_params["id"], request.path_params["toId"]
    store.add_assoc(t, oid, to_t, toid)
    tid = schema.default_assoc_type(t, to_t)
    rtid = schema.default_assoc_type(to_t, t)
    return {"status": "COMPLETE", "results": [
        {"from": {"id": str(oid)}, "to": {"id": str(toid)}, "associationSpec": {"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": tid}},
        {"from": {"id": str(toid)}, "to": {"id": str(oid)}, "associationSpec": {"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": rtid}},
    ], "startedAt": ts(), "completedAt": ts()}


@handler
def v4_assoc_put(request, body):
    t = otype(request)
    to_t = schema.norm_type(request.path_params["toType"])
    oid, toid = request.path_params["id"], request.path_params["toId"]
    specs = body if isinstance(body, list) else ([body] if body else [{}])
    labels = []
    for s in specs:
        tid = s.get("associationTypeId")
        cat = s.get("associationCategory") or "HUBSPOT_DEFINED"
        _validate_type_id(t, to_t, tid, cat)
        store.add_assoc(t, oid, to_t, toid, int(tid) if tid is not None else None, cat)
        lab = store.label_for(int(tid), cat) if tid is not None else None
        if lab:
            labels.append(lab)
    return {"fromObjectTypeId": schema.OBJECT_TYPES[t], "fromObjectId": int(oid), "toObjectTypeId": schema.OBJECT_TYPES[to_t],
            "toObjectId": int(toid), "labels": labels}, 201


def _validate_type_id(t, to_t, tid, cat):
    if tid is None:
        return
    try:
        tid = int(tid)
    except ValueError:
        raise ApiError(400, "associationTypeId must be an integer", "VALIDATION_ERROR")
    if cat == "HUBSPOT_DEFINED":
        valid = [x[0] for x in schema.ASSOC.get((t, to_t), [])]
        if valid and tid not in valid:
            raise ApiError(400, f"associationTypeId {tid} is not valid for {t} to {to_t}", "VALIDATION_ERROR")


@handler
def v4_assoc_delete(request, body):
    t = otype(request)
    to_t = schema.norm_type(request.path_params["toType"])
    store.remove_assoc(t, request.path_params["id"], to_t, request.path_params["toId"])
    return None


@handler
def v3_assoc_list(request, body):
    t = otype(request)
    to_t = schema.norm_type(request.path_params["toType"])
    oid = request.path_params["id"]
    _check_obj(t, oid)
    results = []
    for to_id, types in store.get_assocs(oid, to_t):
        for c, tid, label in types:
            results.append({"id": str(to_id), "type": schema.assoc_type_name(t, to_t) + ("" if not label else "_" + label.lower())})
    return {"results": results}


@handler
def v3_assoc_put(request, body):
    t = otype(request)
    to_t = schema.norm_type(request.path_params["toType"])
    oid, toid, at = request.path_params["id"], request.path_params["toId"], request.path_params["assocType"]
    tid = _resolve_assoc_type(t, to_t, at)
    store.add_assoc(t, oid, to_t, toid, tid)
    o = store.get_obj(t, oid)
    return store.to_api(o, None, [request.path_params["toType"]])


def _resolve_assoc_type(t, to_t, at):
    try:
        return int(at)
    except ValueError:
        pass
    at = str(at).lower()
    if at == schema.assoc_type_name(t, to_t):
        return schema.default_assoc_type(t, to_t)
    return schema.default_assoc_type(t, to_t)


@handler
def v3_assoc_delete(request, body):
    t = otype(request)
    to_t = schema.norm_type(request.path_params["toType"])
    store.remove_assoc(t, request.path_params["id"], to_t, request.path_params["toId"])
    return None


@handler
def v4_batch(request, body):
    f = schema.norm_type(request.path_params["from"])
    to = schema.norm_type(request.path_params["to"])
    action = request.path_params["action"]
    if not f or not to:
        raise ApiError(400, "Unknown object type", "VALIDATION_ERROR")
    inputs = (body or {}).get("inputs") or []
    started = ts()
    results, errors = [], []
    if action == "read":
        for inp in inputs:
            oid = inp.get("id")
            if not store.get_obj(f, oid):
                errors.append({"status": "error", "category": "OBJECT_NOT_FOUND", "message": f"No {f} with id {oid}", "context": {"fromObjectId": [str(oid)]}})
                continue
            r = _v4_results(f, oid, to, 10000)
            results.append({"from": {"id": str(oid)}, "to": r["results"]})
        return _batch_result(results, errors, started)
    if action == "create":
        for inp in inputs:
            fid = (inp.get("from") or {}).get("id")
            tid = (inp.get("to") or {}).get("id")
            types = inp.get("types") or [{}]
            try:
                labels = []
                for ty in types:
                    _validate_type_id(f, to, ty.get("associationTypeId"), ty.get("associationCategory") or "HUBSPOT_DEFINED")
                    store.add_assoc(f, fid, to, tid, ty.get("associationTypeId") and int(ty["associationTypeId"]), ty.get("associationCategory") or "HUBSPOT_DEFINED")
                results.append({"fromObjectTypeId": schema.OBJECT_TYPES[f], "fromObjectId": int(fid), "toObjectTypeId": schema.OBJECT_TYPES[to], "toObjectId": int(tid), "labels": labels})
            except ApiError as e:
                errors.append(e.body())
        if errors and not results:
            raise ApiError(400, errors[0]["message"], errors[0]["category"])
        return _batch_result(results, errors, started, 201)
    if action == "associate/default" or action == "associate":
        for inp in inputs:
            fid = (inp.get("from") or {}).get("id")
            tid = (inp.get("to") or {}).get("id")
            try:
                store.add_assoc(f, fid, to, tid)
                results.append({"from": {"id": str(fid)}, "to": {"id": str(tid)}, "associationSpec": {"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": schema.default_assoc_type(f, to)}})
            except ApiError as e:
                errors.append(e.body())
        return _batch_result(results, errors, started)
    if action in ("archive", "labels/archive"):
        for inp in inputs:
            fid = (inp.get("from") or {}).get("id")
            tos = inp.get("to")
            if isinstance(tos, dict):
                tos = [tos]
            for tt in tos or []:
                tid = tt.get("id")
                if action == "labels/archive":
                    for ty in inp.get("types") or []:
                        store.remove_assoc(f, fid, to, tid, int(ty.get("associationTypeId")))
                else:
                    store.remove_assoc(f, fid, to, tid)
        return None
    raise ApiError(404, "Unknown action", "OBJECT_NOT_FOUND")


@handler
def v3_assoc_batch(request, body):
    f = schema.norm_type(request.path_params["from"])
    to = schema.norm_type(request.path_params["to"])
    action = request.path_params["action"]
    inputs = (body or {}).get("inputs") or []
    started = ts()
    results = []
    if action == "read":
        for inp in inputs:
            oid = inp.get("id")
            lst = store.get_assocs(oid, to)
            results.append({"from": {"id": str(oid)}, "to": [{"id": str(i), "type": schema.assoc_type_name(f, to)} for i, _ in lst]})
        return _batch_result(results, [], started)
    if action == "create":
        for inp in inputs:
            fid = (inp.get("from") or {}).get("id")
            tid = (inp.get("to") or {}).get("id")
            store.add_assoc(f, fid, to, tid, _resolve_assoc_type(f, to, inp.get("type") or ""))
            results.append({"from": {"id": str(fid)}, "to": {"id": str(tid)}, "type": inp.get("type") or schema.assoc_type_name(f, to)})
        return _batch_result(results, [], started, 201)
    if action == "archive":
        for inp in inputs:
            store.remove_assoc(f, (inp.get("from") or {}).get("id"), to, (inp.get("to") or {}).get("id"))
        return None
    raise ApiError(404, "Unknown action", "OBJECT_NOT_FOUND")


@handler
def assoc_labels(request, body):
    f = schema.norm_type(request.path_params["from"])
    to = schema.norm_type(request.path_params["to"])
    if not f or not to:
        raise ApiError(400, "Unknown object type", "VALIDATION_ERROR")
    if request.method == "GET":
        res = [{"category": "HUBSPOT_DEFINED", "typeId": tid, "label": label} for tid, label in schema.ASSOC.get((f, to), [])]
        for tid, label, cat in store.rconn().execute("SELECT type_id,label,category FROM labels WHERE from_type=? AND to_type=?", (f, to)):
            res.append({"category": cat, "typeId": tid, "label": label})
        return {"results": res}
    if request.method == "POST":
        body = body or {}
        label = body.get("label") or body.get("name")
        if not label:
            raise ApiError(400, "label is required", "VALIDATION_ERROR")
        tid = store.next_id() % 100000 + 1000
        rid = tid + 1 if f != to else tid
        with store.W:
            store.wconn.execute("INSERT INTO labels VALUES(?,?,?,?,?)", (f, to, tid, label, "USER_DEFINED"))
            if f != to:
                store.wconn.execute("INSERT INTO labels VALUES(?,?,?,?,?)", (to, f, rid, body.get("inverseLabel") or label, "USER_DEFINED"))
        res = [{"category": "USER_DEFINED", "typeId": tid, "label": label}]
        return {"results": res}, 200
    if request.method == "PUT":
        body = body or {}
        with store.W:
            store.wconn.execute("UPDATE labels SET label=? WHERE type_id=?", (body.get("label"), int(body.get("associationTypeId"))))
        return None
    raise ApiError(405, "Method not allowed")


@handler
def assoc_label_delete(request, body):
    with store.W:
        store.wconn.execute("DELETE FROM labels WHERE type_id=?", (int(request.path_params["typeId"]),))
    return None


@handler
def v3_assoc_types(request, body):
    f = schema.norm_type(request.path_params["from"])
    to = schema.norm_type(request.path_params["to"])
    return {"results": [{"id": str(tid), "name": schema.assoc_type_name(f, to) + ("" if not label else "_" + label.lower())} for tid, label in schema.ASSOC.get((f, to), [])]}


# ------------------------------------------------------------------ properties
def _prop_out(p):
    p = dict(p)
    p.setdefault("modificationMetadata", {"archivable": True, "readOnlyDefinition": not p["name"].startswith(("id_", "commerciale", "assegnatario", "autore", "partita_iva", "fatturato", "classe")), "readOnlyValue": False})
    return p


@handler
def props_list(request, body):
    t = otype(request)
    return {"results": [_prop_out(p) for p in store.defs(t).values()]}


VALID_TYPES = {"string", "number", "date", "datetime", "enumeration", "bool", "phone_number"}


@handler
def props_create(request, body):
    t = otype(request)
    p = _prop_create(t, body or {})
    return _prop_out(p), 201


def _prop_create(t, body):
    name = body.get("name")
    for k in ("name", "label", "type", "fieldType", "groupName"):
        if not body.get(k):
            raise ApiError(400, f"Invalid input JSON: missing required field {k}", "VALIDATION_ERROR")
    if body["type"] not in VALID_TYPES:
        raise ApiError(400, f"Invalid property type {body['type']}", "VALIDATION_ERROR")
    if name in store.defs(t):
        raise ApiError(409, f"Property named '{name}' already exists.", "OBJECT_ALREADY_EXISTS")
    now = ts()
    p = {"name": name, "label": body["label"], "type": body["type"], "fieldType": body["fieldType"], "groupName": body["groupName"],
         "description": body.get("description", ""), "options": body.get("options") or [], "hasUniqueValue": bool(body.get("hasUniqueValue")),
         "hidden": bool(body.get("hidden")), "formField": bool(body.get("formField")), "displayOrder": body.get("displayOrder", -1),
         "calculated": False, "externalOptions": False, "createdAt": now, "updatedAt": now, "archived": False,
         "createdUserId": "0", "updatedUserId": "0"}
    store.save_propdef(t, p)
    return p


@handler
def prop_get(request, body):
    t = otype(request)
    p = store.defs(t).get(request.path_params["name"])
    if not p:
        raise not_found(f"Unable to find property {request.path_params['name']}")
    return _prop_out(p)


@handler
def prop_update(request, body):
    t = otype(request)
    name = request.path_params["name"]
    p = store.defs(t).get(name)
    if not p:
        raise not_found(f"Unable to find property {name}")
    p = dict(p)
    for k in ("label", "description", "groupName", "options", "displayOrder", "hidden", "formField", "type", "fieldType"):
        if k in (body or {}):
            p[k] = body[k]
    p["updatedAt"] = ts()
    store.save_propdef(t, p)
    return _prop_out(p)


@handler
def prop_delete(request, body):
    t = otype(request)
    name = request.path_params["name"]
    if name not in store.defs(t):
        raise not_found(f"Unable to find property {name}")
    store.delete_propdef(t, name)
    return None


@handler
def props_batch(request, body):
    t = otype(request)
    action = request.path_params["action"]
    inputs = (body or {}).get("inputs") or []
    started = ts()
    if action == "read":
        d = store.defs(t)
        return _batch_result([_prop_out(d[i["name"]]) for i in inputs if i.get("name") in d], [], started)
    if action == "create":
        return _batch_result([_prop_out(_prop_create(t, i)) for i in inputs], [], started, 201)
    if action == "archive":
        for i in inputs:
            store.delete_propdef(t, i.get("name"))
        return None
    raise ApiError(404, "Unknown action", "OBJECT_NOT_FOUND")


@handler
def groups(request, body):
    t = otype(request)
    if request.method == "GET":
        return {"results": [json.loads(r[0]) for r in store.rconn().execute("SELECT json FROM propgroups WHERE type=?", (t,))]}
    body = body or {}
    if not body.get("name") or not body.get("label"):
        raise ApiError(400, "name and label are required", "VALIDATION_ERROR")
    g = {"name": body["name"], "label": body["label"], "displayOrder": body.get("displayOrder", -1), "archived": False}
    with store.W:
        if store.wconn.execute("SELECT 1 FROM propgroups WHERE type=? AND name=?", (t, g["name"])).fetchone():
            raise ApiError(409, f"Group {g['name']} already exists", "OBJECT_ALREADY_EXISTS")
        store.wconn.execute("INSERT INTO propgroups VALUES(?,?,?)", (t, g["name"], json.dumps(g)))
    return g, 201


@handler
def group_one(request, body):
    t = otype(request)
    name = request.path_params["name"]
    r = store.rconn().execute("SELECT json FROM propgroups WHERE type=? AND name=?", (t, name)).fetchone()
    if not r:
        raise not_found(f"Group {name} not found")
    g = json.loads(r[0])
    if request.method == "GET":
        return g
    if request.method == "DELETE":
        with store.W:
            store.wconn.execute("DELETE FROM propgroups WHERE type=? AND name=?", (t, name))
        return None
    g.update({k: v for k, v in (body or {}).items() if k in ("label", "displayOrder")})
    with store.W:
        store.wconn.execute("UPDATE propgroups SET json=? WHERE type=? AND name=?", (json.dumps(g), t, name))
    return g


# ------------------------------------------------------------------ pipelines
def ptype(request):
    t = schema.norm_type(request.path_params["type"])
    if t not in ("deals", "tickets"):
        raise ApiError(400, f"Object type {request.path_params['type']} does not support pipelines", "VALIDATION_ERROR")
    return t


def _mk_stage(t, s, i):
    now = ts()
    md = dict(s.get("metadata") or {})
    if t == "deals":
        if "probability" not in md:
            raise ApiError(400, "Deal stage metadata.probability is required", "VALIDATION_ERROR")
        md["probability"] = str(md["probability"])
        md.setdefault("isClosed", "true" if float(md["probability"]) in (0.0, 1.0) and md.get("isClosed") in (True, "true") else str(md.get("isClosed", "false")).lower())
        md["isClosed"] = str(md["isClosed"]).lower()
    else:
        md.setdefault("ticketState", "OPEN")
        md["isClosed"] = "true" if md.get("ticketState") == "CLOSED" else "false"
    if not s.get("label"):
        raise ApiError(400, "Stage label is required", "VALIDATION_ERROR")
    return {"id": str(s.get("id") or store.new_small_id()), "label": s["label"], "displayOrder": s.get("displayOrder", i),
            "metadata": md, "createdAt": now, "updatedAt": now, "archived": False}


@handler
def pipelines_list(request, body):
    t = ptype(request)
    if request.method == "GET":
        return {"results": store.pipelines(t)}
    body = body or {}
    if not body.get("label") or not isinstance(body.get("stages"), list):
        raise ApiError(400, "label and stages are required", "VALIDATION_ERROR")
    if store.pipeline_by_label(t, body["label"]):
        raise ApiError(409, f"A pipeline with label {body['label']} already exists", "CONFLICT")
    now = ts()
    pl = {"id": store.new_small_id(), "label": body["label"], "displayOrder": body.get("displayOrder", len(store.pipelines(t))),
          "stages": [_mk_stage(t, s, i) for i, s in enumerate(body["stages"])], "createdAt": now, "updatedAt": now, "archived": False}
    store.pipeline_save(t, pl)
    return pl, 201


@handler
def pipeline_one(request, body):
    t = ptype(request)
    pl = store.pipeline_get(t, request.path_params["pid"])
    if not pl:
        raise not_found(f"Pipeline {request.path_params['pid']} not found")
    if request.method == "GET":
        return pl
    if request.method == "DELETE":
        store.pipeline_delete(t, pl["id"])
        return None
    body = body or {}
    pl = json.loads(json.dumps(pl))
    if "label" in body:
        pl["label"] = body["label"]
    if "displayOrder" in body:
        pl["displayOrder"] = body["displayOrder"]
    if request.method == "PUT" and "stages" in body:
        pl["stages"] = [_mk_stage(t, s, i) for i, s in enumerate(body["stages"])]
    pl["updatedAt"] = ts()
    store.pipeline_save(t, pl)
    return pl


@handler
def stages(request, body):
    t = ptype(request)
    pl = store.pipeline_get(t, request.path_params["pid"])
    if not pl:
        raise not_found("Pipeline not found")
    if request.method == "GET":
        return {"results": pl["stages"]}
    pl = json.loads(json.dumps(pl))
    s = _mk_stage(t, body or {}, len(pl["stages"]))
    pl["stages"].append(s)
    store.pipeline_save(t, pl)
    return s, 201


@handler
def stage_one(request, body):
    t = ptype(request)
    pl = store.pipeline_get(t, request.path_params["pid"])
    if not pl:
        raise not_found("Pipeline not found")
    pl = json.loads(json.dumps(pl))
    sid = request.path_params["sid"]
    for i, s in enumerate(pl["stages"]):
        if s["id"] == sid:
            if request.method == "GET":
                return s
            if request.method == "DELETE":
                pl["stages"].pop(i)
                store.pipeline_save(t, pl)
                return None
            body = body or {}
            for k in ("label", "displayOrder"):
                if k in body:
                    s[k] = body[k]
            if "metadata" in body:
                s["metadata"].update({k: str(v).lower() if isinstance(v, bool) else str(v) for k, v in body["metadata"].items()})
            s["updatedAt"] = ts()
            store.pipeline_save(t, pl)
            return s
    raise not_found(f"Stage {sid} not found")


# ------------------------------------------------------------------ owners
@handler
def owners(request, body):
    rows = store.rconn().execute("SELECT json FROM owners ORDER BY id").fetchall()
    res = [json.loads(r[0]) for r in rows]
    email = request.query_params.get("email")
    if email:
        res = [o for o in res if o.get("email", "").lower() == email.lower()]
    archived = request.query_params.get("archived", "false").lower() == "true"
    res = [o for o in res if bool(o.get("archived")) == archived]
    limit = int(request.query_params.get("limit", 100))
    start = int(request.query_params.get("after") or 0)
    page = res[start:start + limit]
    out = {"results": page}
    if start + limit < len(res):
        out["paging"] = {"next": {"after": str(start + limit)}}
    return out


@handler
def owner_one(request, body):
    r = store.rconn().execute("SELECT json FROM owners WHERE id=?", (request.path_params["id"],)).fetchone()
    if not r:
        raise not_found("Owner not found")
    return json.loads(r[0])


# ------------------------------------------------------------------ lists
def _list_get(lid):
    r = store.rconn().execute("SELECT json FROM lists WHERE id=?", (int(lid),)).fetchone() if str(lid).isdigit() else None
    if not r:
        raise not_found(f"List {lid} does not exist")
    return json.loads(r[0])


def _list_size(l):
    if l.get("processingType") == "DYNAMIC" and l.get("filterBranch"):
        return len(_dynamic_members(l))
    return store.rconn().execute("SELECT count(*) FROM list_members WHERE list_id=?", (int(l["listId"]),)).fetchone()[0]


def _list_out(l):
    l = dict(l)
    l["size"] = _list_size(l)
    return l


def _dynamic_members(l):
    t = schema.TYPE_BY_ID.get(l["objectTypeId"])
    groups = _branch_to_groups(l.get("filterBranch") or {})
    if groups is None:
        return [r[0] for r in store.rconn().execute("SELECT obj_id FROM list_members WHERE list_id=?", (int(l["listId"]),))]
    ids = []
    after = 0
    while True:
        total, objs, nxt = store.search(t, {"filterGroups": groups, "limit": 200, "after": after})
        ids.extend(o["id"] for o in objs)
        if not nxt:
            break
        after = int(nxt)
    return ids


def _branch_to_groups(fb):
    """Translate a simple OR(AND(property filters)) filterBranch into search filterGroups."""
    try:
        groups = []
        branches = fb.get("filterBranches") or []
        if fb.get("filterBranchType") == "AND":
            branches = [fb]
        for b in branches:
            fl = []
            for f in b.get("filters") or []:
                if f.get("filterType") != "PROPERTY":
                    return None
                op = f.get("operation") or {}
                oper = (op.get("operator") or "").upper()
                m = {"IS_EQUAL_TO": "EQ", "IS_NOT_EQUAL_TO": "NEQ", "IS_KNOWN": "HAS_PROPERTY", "IS_UNKNOWN": "NOT_HAS_PROPERTY",
                     "IS_GREATER_THAN": "GT", "IS_LESS_THAN": "LT", "IS_GREATER_THAN_OR_EQUAL_TO": "GTE", "IS_LESS_THAN_OR_EQUAL_TO": "LTE",
                     "IS_ANY_OF": "IN", "IS_NONE_OF": "NOT_IN", "CONTAINS": "CONTAINS_TOKEN", "HAS_PROPERTY": "HAS_PROPERTY",
                     "NOT_HAS_PROPERTY": "NOT_HAS_PROPERTY", "EQ": "EQ", "NEQ": "NEQ", "GT": "GT", "LT": "LT", "IN": "IN"}.get(oper)
                if not m:
                    return None
                flt = {"propertyName": f.get("property"), "operator": m}
                if "values" in op:
                    flt["values"] = op["values"]
                    if m in ("EQ", "NEQ"):
                        flt["value"] = op["values"][0]
                if "value" in op:
                    flt["value"] = op["value"]
                fl.append(flt)
            if fl:
                groups.append({"filters": fl})
        return groups
    except Exception:
        return None


@handler
def lists_create(request, body):
    body = body or {}
    if not body.get("name") or not body.get("objectTypeId") or not body.get("processingType"):
        raise ApiError(400, "name, objectTypeId and processingType are required", "VALIDATION_ERROR")
    otid = body["objectTypeId"]
    if otid not in schema.TYPE_BY_ID:
        nt = schema.norm_type(otid)
        if not nt:
            raise ApiError(400, f"Invalid objectTypeId {otid}", "VALIDATION_ERROR")
        otid = schema.OBJECT_TYPES[nt]
    if body["processingType"] not in ("MANUAL", "DYNAMIC", "SNAPSHOT"):
        raise ApiError(400, "processingType must be MANUAL, DYNAMIC or SNAPSHOT", "VALIDATION_ERROR")
    return {"list": _list_out(create_list(body["name"], otid, body["processingType"], body.get("filterBranch")))}


def create_list(name, otid, ptype_, filter_branch=None, members=None):
    with store.W:
        for (js,) in store.wconn.execute("SELECT json FROM lists").fetchall():
            if json.loads(js)["name"].lower() == name.lower():
                raise ApiError(409, f"A list named {name} already exists", "CONFLICT")
        lid = store.next_id()
        now = ts()
        l = {"listId": str(lid), "listVersion": 1, "name": name, "objectTypeId": otid, "processingType": ptype_,
             "processingStatus": "COMPLETE", "createdAt": now, "updatedAt": now, "filtersUpdatedAt": now, "deletedAt": None}
        if filter_branch:
            l["filterBranch"] = filter_branch
        store.wconn.execute("INSERT INTO lists(id,json) VALUES(?,?)", (lid, json.dumps(l, ensure_ascii=False)))
        if members:
            store.wconn.executemany("INSERT OR IGNORE INTO list_members VALUES(?,?,?)", [(lid, int(m), now) for m in members])
    return l


@handler
def lists_search(request, body):
    body = body or {}
    q = (body.get("query") or "").lower()
    res = []
    for (js,) in store.rconn().execute("SELECT json FROM lists ORDER BY id"):
        l = json.loads(js)
        if q and q not in l["name"].lower():
            continue
        if body.get("processingTypes") and l["processingType"] not in body["processingTypes"]:
            continue
        res.append(_list_out(l))
    off = int(body.get("offset") or 0)
    cnt = int(body.get("count") or 20)
    page = res[off:off + cnt]
    return {"lists": page, "hasMore": off + cnt < len(res), "offset": off + len(page), "total": len(res)}


@handler
def lists_get_many(request, body):
    ids = qlist(request, "listIds")
    out = []
    for i in ids:
        try:
            out.append(_list_out(_list_get(i)))
        except ApiError:
            pass
    if not ids:
        out = [_list_out(json.loads(js)) for (js,) in store.rconn().execute("SELECT json FROM lists ORDER BY id")]
    return {"lists": out}


@handler
def list_one(request, body):
    l = _list_get(request.path_params["lid"])
    if request.method == "DELETE":
        with store.W:
            store.wconn.execute("DELETE FROM lists WHERE id=?", (int(l["listId"]),))
            store.wconn.execute("DELETE FROM list_members WHERE list_id=?", (int(l["listId"]),))
        return None
    return {"list": _list_out(l)}


@handler
def list_by_name(request, body):
    name = request.path_params["name"]
    otid = request.path_params["otid"]
    for (js,) in store.rconn().execute("SELECT json FROM lists"):
        l = json.loads(js)
        if l["name"].lower() == name.lower() and (l["objectTypeId"] == otid or schema.norm_type(otid) == schema.TYPE_BY_ID.get(l["objectTypeId"])):
            return {"list": _list_out(l)}
    raise not_found(f"List {name} does not exist")


@handler
def list_update_name(request, body):
    l = _list_get(request.path_params["lid"])
    name = request.query_params.get("listName") or (body or {}).get("name")
    if name:
        l["name"] = name
        l["updatedAt"] = ts()
        with store.W:
            store.wconn.execute("UPDATE lists SET json=? WHERE id=?", (json.dumps(l, ensure_ascii=False), int(l["listId"])))
    return {"updatedList": _list_out(l)}


@handler
def list_members(request, body):
    l = _list_get(request.path_params["lid"])
    if l.get("processingType") == "DYNAMIC" and l.get("filterBranch"):
        ids = sorted(_dynamic_members(l))
        rows = [(i, l["updatedAt"]) for i in ids]
    else:
        rows = store.rconn().execute("SELECT obj_id, ts FROM list_members WHERE list_id=? ORDER BY obj_id", (int(l["listId"]),)).fetchall()
    limit = min(int(request.query_params.get("limit", 100)), 250)
    after = request.query_params.get("after")
    start = int(after) if after and after.isdigit() else 0
    page = rows[start:start + limit]
    res = {"results": [{"recordId": str(r[0]), "membershipTimestamp": r[1]} for r in page], "total": len(rows)}
    if start + limit < len(rows):
        res["paging"] = {"next": {"after": str(start + limit)}}
    return res


@handler
def list_members_mod(request, body):
    l = _list_get(request.path_params["lid"])
    action = request.path_params["action"]
    lid = int(l["listId"])
    if l.get("processingType") == "DYNAMIC":
        raise ApiError(400, "Cannot manually modify memberships of a DYNAMIC list", "VALIDATION_ERROR")
    now = ts()
    added, removed = [], []
    with store.W:
        if action in ("add", "add-and-remove"):
            ids = body if isinstance(body, list) else (body or {}).get("recordIdsToAdd", [])
            for i in ids:
                if store.wconn.execute("INSERT OR IGNORE INTO list_members VALUES(?,?,?)", (lid, int(i), now)).rowcount:
                    added.append(str(i))
        if action in ("remove", "add-and-remove"):
            ids = body if isinstance(body, list) else (body or {}).get("recordIdsToRemove", [])
            for i in ids:
                if store.wconn.execute("DELETE FROM list_members WHERE list_id=? AND obj_id=?", (lid, int(i))).rowcount:
                    removed.append(str(i))
        if action == "remove-all":
            store.wconn.execute("DELETE FROM list_members WHERE list_id=?", (lid,))
            return None
    return {"recordIdsAdded": added, "recordIdsRemoved": removed, "recordsIdsAdded": added, "recordsIdsRemoved": removed, "recordIdsMissing": []}


# ------------------------------------------------------------------ exports
@handler
def export_start(request, body):
    body = body or {}
    t = schema.norm_type(body.get("objectType") or "")
    if not t:
        raise ApiError(400, "objectType is required", "VALIDATION_ERROR")
    props = body.get("objectProperties") or ["hs_object_id"]
    jid = str(store.next_id())
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Record ID"] + props)
    after = None
    lid = None
    if body.get("exportType") == "LIST" and body.get("listId"):
        lid = body["listId"]
    if lid:
        ids = [r[0] for r in store.rconn().execute("SELECT obj_id FROM list_members WHERE list_id=?", (int(lid),))]
        for i in ids:
            o = store.get_obj(t, i)
            if o:
                w.writerow([o["id"]] + [o["props"].get(p, "") for p in props])
    else:
        while True:
            objs, after = store.list_objects(t, 1000, after)
            for o in objs:
                w.writerow([o["id"]] + [o["props"].get(p, "") for p in props])
            if not after:
                break
    now = ts()
    job = {"id": jid, "status": "COMPLETE", "requestedAt": now, "startedAt": now, "completedAt": now,
           "result": f"/exports/files/{jid}/{(body.get('exportName') or 'export').replace(' ', '_')}.csv"}
    with store.W:
        store.wconn.execute("INSERT INTO jobs(id,json) VALUES(?,?)", (jid, json.dumps({"job": job, "csv": buf.getvalue()})))
    return {"id": jid, "links": {"status": f"/crm/v3/exports/export/async/tasks/{jid}/status"}}, 202


@handler
def export_status(request, body):
    r = store.rconn().execute("SELECT json FROM jobs WHERE id=?", (request.path_params["id"],)).fetchone()
    if not r:
        raise not_found("Export not found")
    job = json.loads(r[0])["job"]
    base = str(request.base_url).rstrip("/")
    proto = request.headers.get("x-forwarded-proto")
    if proto == "https" and base.startswith("http://"):
        base = "https://" + base[7:]
    out = dict(job)
    out["result"] = base + job["result"]
    return out


async def export_file(request):
    r = store.rconn().execute("SELECT json FROM jobs WHERE id=?", (request.path_params["id"],)).fetchone()
    if not r:
        return J(not_found("File not found").body(), 404)
    return Response(json.loads(r[0])["csv"], media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=export.csv"})


# ------------------------------------------------------------------ imports (CSV, simple)
async def import_start(request):
    try:
        form = await request.form()
        req = json.loads(form.get("importRequest") or "{}")
        files = form.getlist("files")
        total = 0
        jid = str(store.next_id())
        for i, fcfg in enumerate(req.get("files") or [{}]):
            if i >= len(files):
                break
            content = (await files[i].read()).decode("utf-8-sig", "replace")
            mappings = ((fcfg.get("fileImportPage") or {}).get("columnMappings")) or []
            delim = ";" if content.count(";") > content.count(",") else ","
            rows = list(csv.reader(io.StringIO(content), delimiter=delim))
            if not rows:
                continue
            header = rows[0]
            for row in rows[1:]:
                by_type = {}
                for ci, col in enumerate(header):
                    m = next((m for m in mappings if m.get("columnName") == col), None)
                    if not m or ci >= len(row):
                        continue
                    t = schema.TYPE_BY_ID.get(m.get("columnObjectTypeId") or "0-1", "contacts")
                    by_type.setdefault(t, {})[m["propertyName"]] = row[ci]
                for t, props in by_type.items():
                    try:
                        await run_in_threadpool(_import_one, t, props)
                        total += 1
                    except ApiError:
                        pass
        now = ts()
        job = {"id": jid, "state": "DONE", "createdAt": now, "updatedAt": now, "importRequestJson": req,
               "importSource": "API", "metadata": {"counters": {"TOTAL_ROWS": total, "CREATED_OBJECTS": total}}, "optOutImport": False}
        with store.W:
            store.wconn.execute("INSERT INTO jobs(id,json) VALUES(?,?)", ("imp" + jid, json.dumps({"job": job})))
        return J(job, 200)
    except ApiError as e:
        return err(e)
    except Exception as e:
        return err(ApiError(400, f"Invalid import request: {e}", "VALIDATION_ERROR"))


def _import_one(t, props):
    if t == "contacts" and props.get("email"):
        o = store.find_by_prop(t, "email", props["email"])
        if o:
            return store.update(t, o["id"], props)
    return store.create(t, props)


@handler
def import_get(request, body):
    r = store.rconn().execute("SELECT json FROM jobs WHERE id=?", ("imp" + request.path_params["id"],)).fetchone()
    if not r:
        raise not_found("Import not found")
    return json.loads(r[0])["job"]


@handler
def imports_list(request, body):
    return {"results": [json.loads(r[0])["job"] for r in store.rconn().execute("SELECT json FROM jobs WHERE id LIKE 'imp%'")]}


# ------------------------------------------------------------------ admin
@handler
def do_reset(request, body):
    store.reset()
    return None


@handler
def do_migrate(request, body):
    from . import migrate
    url = (body or {}).get("export_url")
    if not url:
        raise ApiError(400, "export_url is required", "VALIDATION_ERROR")
    migrate.migrate_from_url(url)
    return None


@handler
def do_agent(request, body):
    from . import agent
    return {"reply": agent.run(body or {})}


UI_ROUTES = {"companies": "/companies", "contacts": "/contacts", "deals": "/deals", "tickets": "/tickets",
             "dormant": "/dormant", "assistant": "/assistant", "products": "/products"}


async def health(request):
    return J({"status": "ok", "version": "2026-09", "ui": UI_ROUTES})


def routes():
    O = "/crm/v3/objects/{type}"
    r = [
        Route("/health", health, methods=["GET"]),
        Route("/__reset", do_reset, methods=["POST"]),
        Route("/__migrate", do_migrate, methods=["POST"]),
        Route("/__agente", do_agent, methods=["POST"]),
        Route(O, obj_list, methods=["GET"]),
        Route(O, obj_create, methods=["POST"]),
        Route(O + "/search", obj_search, methods=["POST"]),
        Route(O + "/merge", obj_merge, methods=["POST"]),
        Route(O + "/batch/{action}", obj_batch, methods=["POST"]),
        Route(O + "/{id}", obj_get, methods=["GET"]),
        Route(O + "/{id}", obj_update, methods=["PATCH", "PUT"]),
        Route(O + "/{id}", obj_delete, methods=["DELETE"]),
        Route(O + "/{id}/associations/{toType}", v3_assoc_list, methods=["GET"]),
        Route(O + "/{id}/associations/{toType}/{toId}/{assocType}", v3_assoc_put, methods=["PUT"]),
        Route(O + "/{id}/associations/{toType}/{toId}/{assocType}", v3_assoc_delete, methods=["DELETE"]),
        Route("/crm/v4/objects/{type}/{id}/associations/default/{toType}/{toId}", v4_assoc_default, methods=["PUT"]),
        Route("/crm/v4/objects/{type}/{id}/associations/{toType}", v4_assoc_list, methods=["GET"]),
        Route("/crm/v4/objects/{type}/{id}/associations/{toType}/{toId}", v4_assoc_put, methods=["PUT"]),
        Route("/crm/v4/objects/{type}/{id}/associations/{toType}/{toId}", v4_assoc_delete, methods=["DELETE"]),
        Route("/crm/v4/associations/{from}/{to}/labels", assoc_labels, methods=["GET", "POST", "PUT"]),
        Route("/crm/v4/associations/{from}/{to}/labels/{typeId}", assoc_label_delete, methods=["DELETE"]),
        Route("/crm/v4/associations/{from}/{to}/batch/{action:path}", v4_batch, methods=["POST"]),
        Route("/crm/v3/associations/{from}/{to}/batch/{action}", v3_assoc_batch, methods=["POST"]),
        Route("/crm/v3/associations/{from}/{to}/types", v3_assoc_types, methods=["GET"]),
        Route("/crm/v3/properties/{type}", props_list, methods=["GET"]),
        Route("/crm/v3/properties/{type}", props_create, methods=["POST"]),
        Route("/crm/v3/properties/{type}/batch/{action}", props_batch, methods=["POST"]),
        Route("/crm/v3/properties/{type}/groups", groups, methods=["GET", "POST"]),
        Route("/crm/v3/properties/{type}/groups/{name}", group_one, methods=["GET", "PATCH", "DELETE"]),
        Route("/crm/v3/properties/{type}/{name}", prop_get, methods=["GET"]),
        Route("/crm/v3/properties/{type}/{name}", prop_update, methods=["PATCH"]),
        Route("/crm/v3/properties/{type}/{name}", prop_delete, methods=["DELETE"]),
        Route("/crm/v3/pipelines/{type}", pipelines_list, methods=["GET", "POST"]),
        Route("/crm/v3/pipelines/{type}/{pid}", pipeline_one, methods=["GET", "PATCH", "PUT", "DELETE"]),
        Route("/crm/v3/pipelines/{type}/{pid}/stages", stages, methods=["GET", "POST"]),
        Route("/crm/v3/pipelines/{type}/{pid}/stages/{sid}", stage_one, methods=["GET", "PATCH", "PUT", "DELETE"]),
        Route("/crm/v3/owners", owners, methods=["GET"]),
        Route("/crm/v3/owners/", owners, methods=["GET"]),
        Route("/crm/v3/owners/{id}", owner_one, methods=["GET"]),
        Route("/crm/v3/lists", lists_create, methods=["POST"]),
        Route("/crm/v3/lists/", lists_create, methods=["POST"]),
        Route("/crm/v3/lists", lists_get_many, methods=["GET"]),
        Route("/crm/v3/lists/", lists_get_many, methods=["GET"]),
        Route("/crm/v3/lists/search", lists_search, methods=["POST"]),
        Route("/crm/v3/lists/object-type-id/{otid}/name/{name}", list_by_name, methods=["GET"]),
        Route("/crm/v3/lists/{lid}", list_one, methods=["GET", "DELETE"]),
        Route("/crm/v3/lists/{lid}/update-list-name", list_update_name, methods=["PUT"]),
        Route("/crm/v3/lists/{lid}/memberships", list_members, methods=["GET"]),
        Route("/crm/v3/lists/{lid}/memberships/join-order", list_members, methods=["GET"]),
        Route("/crm/v3/lists/{lid}/memberships/{action}", list_members_mod, methods=["PUT", "DELETE"]),
        Route("/crm/v3/lists/{lid}/memberships", list_members_mod, methods=["DELETE"]),
        Route("/crm/v3/exports/export/async", export_start, methods=["POST"]),
        Route("/crm/v3/exports/export/async/tasks/{id}/status", export_status, methods=["GET"]),
        Route("/exports/files/{id}/{name}", export_file, methods=["GET"]),
        Route("/crm/v3/imports", import_start, methods=["POST"]),
        Route("/crm/v3/imports/", import_start, methods=["POST"]),
        Route("/crm/v3/imports", imports_list, methods=["GET"]),
        Route("/crm/v3/imports/{id}", import_get, methods=["GET"]),
    ]
    return r


class AuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope["path"]
            if path.startswith("/crm/") or path.startswith("/__") or path.startswith("/api/"):
                if TOKENS:
                    headers = dict(scope.get("headers") or [])
                    auth = headers.get(b"authorization", b"").decode()
                    tok = auth[7:].strip() if auth.lower().startswith("bearer ") else None
                    if not tok:
                        from urllib.parse import parse_qs
                        qs = parse_qs(scope.get("query_string", b"").decode())
                        tok = (qs.get("hapikey") or qs.get("token") or [None])[0]
                    if tok not in TOKENS:
                        body = {"status": "error", "message": "Authentication credentials not found. This API supports OAuth 2.0 authentication and you can find more details at https://developers.example.com/docs/methods/auth/oauth-overview",
                                "correlationId": str(uuid.uuid4()), "category": "INVALID_AUTHENTICATION"}
                        resp = J(body, 401)
                        await resp(scope, receive, send)
                        return
        await self.app(scope, receive, send)

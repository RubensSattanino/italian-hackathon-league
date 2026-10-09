import json
import uuid

from starlette.applications import Starlette
from starlette.responses import Response

from app import store, api

store.init_db()

try:
    from app import ui
    ui_routes = ui.routes()
except Exception as e:  # pragma: no cover
    import traceback
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route
    _ui_err = traceback.format_exc()
    print("UI disabled:", _ui_err, flush=True)

    async def _ui_broken(request):
        return PlainTextResponse("UI failed to load (the API still works):\n\n" + _ui_err, status_code=500)
    ui_routes = [Route(p, _ui_broken) for p in ("/", "/companies", "/contacts", "/deals", "/tickets", "/dormant", "/products", "/assistant")]


async def not_found(request, exc):
    code = getattr(exc, "status_code", 404)
    body = {"status": "error", "message": "Resource not found" if code == 404 else "Method not allowed",
            "correlationId": str(uuid.uuid4()), "category": "OBJECT_NOT_FOUND" if code == 404 else "VALIDATION_ERROR"}
    return Response(json.dumps(body), status_code=code, media_type="application/json")


async def server_error(request, exc):
    body = {"status": "error", "message": f"Internal error: {exc}", "correlationId": str(uuid.uuid4()), "category": "INTERNAL_ERROR"}
    return Response(json.dumps(body), status_code=500, media_type="application/json")


app = Starlette(routes=api.routes() + ui_routes, exception_handlers={404: not_found, 405: not_found, 500: server_error})
app = api.AuthMiddleware(app)

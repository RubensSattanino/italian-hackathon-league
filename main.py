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
    print("UI disabled:", e)
    ui_routes = []


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

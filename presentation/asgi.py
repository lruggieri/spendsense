"""ASGI entrypoint: serves the MCP server at /mcp and the Flask app at /.

Run with:
    gunicorn -k uvicorn.workers.UvicornWorker -w 4 presentation.asgi:app
or:
    uvicorn presentation.asgi:app
"""
from asgiref.wsgi import WsgiToAsgi
from starlette.types import ASGIApp, Receive, Scope, Send

from presentation.web.app import app as flask_app
from presentation.mcp_server.server import mcp

mcp_app = mcp.streamable_http_app()

# Collect the exact paths FastMCP registered (e.g. "/mcp", "/.well-known/...")
_mcp_paths = frozenset(
    r.path for r in mcp_app.routes if hasattr(r, "path")
)

_flask_asgi: ASGIApp = WsgiToAsgi(flask_app)


class _Dispatcher:
    """Route to FastMCP (preserving its full middleware stack) or Flask by path."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await mcp_app(scope, receive, send)
            return
        if scope["type"] in ("http", "websocket"):
            path: str = scope.get("path", "")
            if path in _mcp_paths or any(path.startswith(p + "/") for p in _mcp_paths):
                await mcp_app(scope, receive, send)
                return
        await _flask_asgi(scope, receive, send)


app = _Dispatcher()

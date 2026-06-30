"""ASGI entrypoint: serves the MCP server at /mcp and the Flask app at /.

Run with:
    gunicorn -k uvicorn.workers.UvicornWorker -w 4 presentation.asgi:app
or:
    uvicorn presentation.asgi:app
"""
from asgiref.wsgi import WsgiToAsgi
from starlette.applications import Starlette
from starlette.routing import Mount

from presentation.web.app import app as flask_app
from presentation.mcp_server.server import mcp

# FastMCP registers its routes at /mcp and /.well-known/... internally.
# Include them directly at the top level — sub-mounting would double the path to /mcp/mcp.
mcp_app = mcp.streamable_http_app()

app = Starlette(
    routes=[
        *mcp_app.routes,
        Mount("/", app=WsgiToAsgi(flask_app)),
    ],
    lifespan=mcp_app.router.lifespan_context,
)

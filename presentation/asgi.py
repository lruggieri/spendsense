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
from presentation.mcp.server import mcp

# /mcp MUST precede the "/" catch-all or Flask swallows MCP requests.
mcp_app = mcp.streamable_http_app()

app = Starlette(
    routes=[
        Mount("/mcp", app=mcp_app),
        Mount("/", app=WsgiToAsgi(flask_app)),
    ],
    lifespan=getattr(mcp_app, "lifespan", None),
)

"""Smoke test for the ASGI entrypoint module structure."""
import ast
import pathlib


def test_asgi_module_parses():
    """The ASGI entrypoint must be syntactically valid Python."""
    src = pathlib.Path("presentation/asgi.py").read_text()
    ast.parse(src)  # raises SyntaxError if invalid


def test_asgi_imports_expected_symbols():
    """The ASGI entrypoint must import the required symbols."""
    src = pathlib.Path("presentation/asgi.py").read_text()
    assert "WsgiToAsgi" in src
    assert "Mount" in src
    assert "streamable_http_app" in src
    assert 'Mount("/mcp"' in src
    assert 'Mount("/"' in src

"""Adaptador WSGI para o Vercel preservar a rota original do Flask."""
from web import app as flask_app


def app(environ, start_response):
    # O rewrite envia a rota original no parâmetro interno `path`.
    query = environ.get("QUERY_STRING", "")
    params = dict(item.split("=", 1) if "=" in item else (item, "") for item in query.split("&") if item)
    has_path = "path" in params
    path = params.pop("path", "")
    if has_path:
        environ["PATH_INFO"] = "/" + path.lstrip("/")
        environ["QUERY_STRING"] = "&".join(f"{key}={value}" for key, value in params.items())
    return flask_app(environ, start_response)

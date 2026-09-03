"""Adaptador WSGI para o Vercel preservar a rota original do Flask."""

from urllib.parse import parse_qsl, urlencode

from web import app as flask_app


def app(environ, start_response):
    """Restaura a rota original enviada pelo rewrite da Vercel.

    A Vercel envia barras de URLs com identificadores como ``%2F`` dentro de
    ``path``. ``parse_qsl`` faz a decodificação correta antes de repassar a
    requisição ao Flask; sem isso, por exemplo, /usuarios/5/editar virava 404.
    """
    parametros = parse_qsl(environ.get("QUERY_STRING", ""), keep_blank_values=True)
    caminho = ""
    parametros_restantes = []
    for chave, valor in parametros:
        if chave == "path" and not caminho:
            caminho = valor
        else:
            parametros_restantes.append((chave, valor))

    if caminho:
        environ["PATH_INFO"] = "/" + caminho.lstrip("/")
        environ["QUERY_STRING"] = urlencode(parametros_restantes)
    return flask_app(environ, start_response)

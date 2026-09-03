"""Migra os dados históricos do SQLite local para um PostgreSQL vazio do Neon.

Uso no PowerShell (não envie a URL para o GitHub):
  $env:DATABASE_URL='postgresql://...'
  python migrar_para_neon.py
"""

import os
import sqlite3

URL = os.environ.get("DATABASE_URL", "")
ARQUIVO_SQLITE = os.path.join(os.path.dirname(__file__), "despesas.db")
TABELAS = [
    "empresas",
    "usuarios",
    "usuario_empresas",
    "motoristas",
    "veiculos",
    "viagens",
    "despesas",
    "anexos_despesa",
    "pagamentos",
    "categorias_despesa",
    "auditoria",
    "cargas",
]


def main():
    if not URL.startswith(("postgres://", "postgresql://")):
        raise SystemExit(
            "Defina DATABASE_URL com a URL de conexão do Neon antes de executar."
        )
    if not os.path.exists(ARQUIVO_SQLITE):
        raise SystemExit("O arquivo despesas.db não foi encontrado nesta pasta.")

    # Cria o schema PostgreSQL do projeto antes de receber os dados.
    import database as db

    db.inicializar()

    from psycopg import connect

    origem = sqlite3.connect(ARQUIVO_SQLITE)
    origem.row_factory = sqlite3.Row
    destino = connect(URL)
    try:
        with destino.cursor() as cur:
            cur.execute(
                "TRUNCATE TABLE " + ", ".join(TABELAS) + " RESTART IDENTITY CASCADE"
            )
            for tabela in TABELAS:
                linhas = origem.execute(f"SELECT * FROM {tabela}").fetchall()
                if not linhas:
                    continue
                colunas = list(linhas[0].keys())
                campos = ", ".join(colunas)
                marcadores = ", ".join(["%s"] * len(colunas))
                cur.executemany(
                    f"INSERT INTO {tabela} ({campos}) VALUES ({marcadores})",
                    [tuple(linha[coluna] for coluna in colunas) for linha in linhas],
                )
                print(f"{tabela}: {len(linhas)} registro(s)")
            for tabela in TABELAS:
                (
                    cur.execute(
                        "SELECT setval(pg_get_serial_sequence(%s, 'id'), "
                        "COALESCE((SELECT MAX(id) FROM " + tabela + "), 1), true)",
                        (tabela,),
                    )
                    if tabela not in ("usuario_empresas",)
                    else None
                )
        destino.commit()
        print("\nMigração concluída com sucesso.")
    except Exception:
        destino.rollback()
        raise
    finally:
        origem.close()
        destino.close()


if __name__ == "__main__":
    main()

import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "despesas.db")

EMPRESAS_PADRAO = ["MARK", "ERIMAR"]

CATEGORIAS = [
    "DIARIA", "REFEICAO", "CHAPA", "COMBUSTIVEL", "ARLA", "PECA", "SINISTRO",
    "PEDAGIO", "BORRACHARIA", "FRETEIRO", "HOSPEDAGEM", "UBER", "OUTROS",
]

LOCAIS_ABASTECIMENTO = ["ASSIS", "VIAGEM"]

TIPOS_CARGA = ["ENTREGA", "COLETA"]

FORMAS_PAGAMENTO = ["DINHEIRO", "CARTAO"]


def conectar():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def inicializar():
    conn = conectar()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS empresas (
        id INTEGER PRIMARY KEY,
        nome TEXT NOT NULL UNIQUE
    );

    CREATE TABLE IF NOT EXISTS motoristas (
        id INTEGER PRIMARY KEY,
        nome TEXT NOT NULL,
        codigo TEXT,
        empresa_id INTEGER NOT NULL REFERENCES empresas(id)
    );

    CREATE TABLE IF NOT EXISTS veiculos (
        id INTEGER PRIMARY KEY,
        placa TEXT NOT NULL,
        codigo TEXT,
        descricao TEXT,
        empresa_id INTEGER NOT NULL REFERENCES empresas(id)
    );

    CREATE TABLE IF NOT EXISTS viagens (
        id INTEGER PRIMARY KEY,
        empresa_id INTEGER NOT NULL REFERENCES empresas(id),
        motorista_id INTEGER NOT NULL REFERENCES motoristas(id),
        veiculo_id INTEGER NOT NULL REFERENCES veiculos(id),
        data_inicio TEXT NOT NULL,
        data_fim TEXT,
        origem TEXT,
        destino TEXT,
        hodometro_inicio REAL NOT NULL,
        hodometro_fim REAL,
        media_computador_bordo REAL,
        valor_adiantamento REAL DEFAULT 0,
        valor_devolvido REAL DEFAULT 0,
        valor_nf_ida REAL DEFAULT 0,
        valor_nf_retorno REAL DEFAULT 0,
        observacoes TEXT
    );

    CREATE TABLE IF NOT EXISTS despesas (
        id INTEGER PRIMARY KEY,
        viagem_id INTEGER NOT NULL REFERENCES viagens(id),
        categoria TEXT NOT NULL,
        data TEXT NOT NULL,
        valor REAL NOT NULL,
        litros REAL,
        local_abastecimento TEXT,
        forma_pagamento TEXT,
        descricao TEXT
    );

    CREATE TABLE IF NOT EXISTS cargas (
        id INTEGER PRIMARY KEY,
        viagem_id INTEGER NOT NULL REFERENCES viagens(id),
        empresa_cliente TEXT NOT NULL,
        tipo TEXT NOT NULL,
        data TEXT NOT NULL,
        valor REAL NOT NULL,
        descricao TEXT
    );
    """)
    for nome in EMPRESAS_PADRAO:
        conn.execute("INSERT OR IGNORE INTO empresas (nome) VALUES (?)", (nome,))

    # migracao: adiciona colunas novas em bancos ja existentes (nao apaga dados)
    colunas_viagens = {row[1] for row in conn.execute("PRAGMA table_info(viagens)")}
    if "valor_nf_ida" not in colunas_viagens:
        conn.execute("ALTER TABLE viagens ADD COLUMN valor_nf_ida REAL DEFAULT 0")
    if "valor_nf_retorno" not in colunas_viagens:
        conn.execute("ALTER TABLE viagens ADD COLUMN valor_nf_retorno REAL DEFAULT 0")
    colunas_despesas = {row[1] for row in conn.execute("PRAGMA table_info(despesas)")}
    if "local_abastecimento" not in colunas_despesas:
        conn.execute("ALTER TABLE despesas ADD COLUMN local_abastecimento TEXT")
    if "forma_pagamento" not in colunas_despesas:
        conn.execute("ALTER TABLE despesas ADD COLUMN forma_pagamento TEXT")
    colunas_motoristas = {row[1] for row in conn.execute("PRAGMA table_info(motoristas)")}
    if "codigo" not in colunas_motoristas:
        conn.execute("ALTER TABLE motoristas ADD COLUMN codigo TEXT")
    colunas_veiculos = {row[1] for row in conn.execute("PRAGMA table_info(veiculos)")}
    if "codigo" not in colunas_veiculos:
        conn.execute("ALTER TABLE veiculos ADD COLUMN codigo TEXT")

    conn.commit()
    conn.close()


def listar_empresas():
    conn = conectar()
    rows = conn.execute("SELECT * FROM empresas ORDER BY nome").fetchall()
    conn.close()
    return rows


def obter_ou_criar_motorista(nome: str, empresa_id: int, codigo: str = "") -> int:
    conn = conectar()
    row = conn.execute(
        "SELECT id FROM motoristas WHERE nome = ? AND empresa_id = ?", (nome, empresa_id)
    ).fetchone()
    if row:
        if codigo:
            conn.execute("UPDATE motoristas SET codigo = ? WHERE id = ?", (codigo, row["id"]))
            conn.commit()
        conn.close()
        return row["id"]
    cur = conn.execute(
        "INSERT INTO motoristas (nome, codigo, empresa_id) VALUES (?, ?, ?)", (nome, codigo or None, empresa_id)
    )
    conn.commit()
    novo_id = cur.lastrowid
    conn.close()
    return novo_id


def listar_motoristas(empresa_id: int):
    conn = conectar()
    rows = conn.execute(
        "SELECT * FROM motoristas WHERE empresa_id = ? ORDER BY nome", (empresa_id,)
    ).fetchall()
    conn.close()
    return rows


def obter_ou_criar_veiculo(placa: str, empresa_id: int, descricao: str = "", codigo: str = "") -> int:
    placa = placa.strip().upper()
    conn = conectar()
    row = conn.execute(
        "SELECT id FROM veiculos WHERE placa = ? AND empresa_id = ?", (placa, empresa_id)
    ).fetchone()
    if row:
        if codigo:
            conn.execute("UPDATE veiculos SET codigo = ? WHERE id = ?", (codigo, row["id"]))
            conn.commit()
        conn.close()
        return row["id"]
    cur = conn.execute(
        "INSERT INTO veiculos (placa, codigo, descricao, empresa_id) VALUES (?, ?, ?, ?)",
        (placa, codigo or None, descricao, empresa_id),
    )
    conn.commit()
    novo_id = cur.lastrowid
    conn.close()
    return novo_id


def listar_veiculos(empresa_id: int):
    conn = conectar()
    rows = conn.execute(
        "SELECT * FROM veiculos WHERE empresa_id = ? ORDER BY placa", (empresa_id,)
    ).fetchall()
    conn.close()
    return rows


def criar_viagem(**kwargs) -> int:
    conn = conectar()
    kwargs.setdefault("valor_adiantamento", 0)
    kwargs.setdefault("valor_nf_ida", 0)
    kwargs.setdefault("valor_nf_retorno", 0)
    cur = conn.execute(
        """INSERT INTO viagens
        (empresa_id, motorista_id, veiculo_id, data_inicio, data_fim, origem, destino,
         hodometro_inicio, hodometro_fim, media_computador_bordo, valor_adiantamento,
         valor_nf_ida, valor_nf_retorno, observacoes)
        VALUES (:empresa_id, :motorista_id, :veiculo_id, :data_inicio, :data_fim, :origem, :destino,
                :hodometro_inicio, :hodometro_fim, :media_computador_bordo, :valor_adiantamento,
                :valor_nf_ida, :valor_nf_retorno, :observacoes)""",
        kwargs,
    )
    conn.commit()
    novo_id = cur.lastrowid
    conn.close()
    return novo_id


def atualizar_viagem(viagem_id: int, **kwargs):
    kwargs["id"] = viagem_id
    kwargs.setdefault("valor_devolvido", 0)
    kwargs.setdefault("valor_nf_ida", 0)
    kwargs.setdefault("valor_nf_retorno", 0)
    conn = conectar()
    conn.execute(
        """UPDATE viagens SET data_fim=:data_fim, hodometro_fim=:hodometro_fim,
        media_computador_bordo=:media_computador_bordo, valor_devolvido=:valor_devolvido,
        valor_nf_ida=:valor_nf_ida, valor_nf_retorno=:valor_nf_retorno,
        observacoes=:observacoes
        WHERE id=:id""",
        kwargs,
    )
    conn.commit()
    conn.close()


def listar_viagens(empresa_id: int = None, abertas_apenas: bool = False):
    conn = conectar()
    query = """
        SELECT v.*, e.nome AS empresa_nome, m.nome AS motorista_nome, m.codigo AS motorista_codigo, ve.placa AS veiculo_placa, ve.codigo AS veiculo_codigo
        FROM viagens v
        JOIN empresas e ON e.id = v.empresa_id
        JOIN motoristas m ON m.id = v.motorista_id
        JOIN veiculos ve ON ve.id = v.veiculo_id
        WHERE 1=1
    """
    params = []
    if empresa_id:
        query += " AND v.empresa_id = ?"
        params.append(empresa_id)
    if abertas_apenas:
        query += " AND v.hodometro_fim IS NULL"
    query += " ORDER BY v.data_inicio DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return rows


def obter_viagem(viagem_id: int):
    conn = conectar()
    row = conn.execute(
        """SELECT v.*, e.nome AS empresa_nome, m.nome AS motorista_nome, m.codigo AS motorista_codigo, ve.placa AS veiculo_placa, ve.codigo AS veiculo_codigo
        FROM viagens v
        JOIN empresas e ON e.id = v.empresa_id
        JOIN motoristas m ON m.id = v.motorista_id
        JOIN veiculos ve ON ve.id = v.veiculo_id
        WHERE v.id = ?""",
        (viagem_id,),
    ).fetchone()
    conn.close()
    return row


def criar_despesa(**kwargs) -> int:
    conn = conectar()
    kwargs.setdefault("local_abastecimento", None)
    kwargs.setdefault("forma_pagamento", None)
    cur = conn.execute(
        """INSERT INTO despesas (viagem_id, categoria, data, valor, litros, local_abastecimento, forma_pagamento, descricao)
        VALUES (:viagem_id, :categoria, :data, :valor, :litros, :local_abastecimento, :forma_pagamento, :descricao)""",
        kwargs,
    )
    conn.commit()
    novo_id = cur.lastrowid
    conn.close()
    return novo_id


def listar_despesas(viagem_id: int = None):
    conn = conectar()
    if viagem_id:
        rows = conn.execute(
            "SELECT * FROM despesas WHERE viagem_id = ? ORDER BY data", (viagem_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT d.*, v.empresa_id, v.motorista_id, v.veiculo_id
            FROM despesas d JOIN viagens v ON v.id = d.viagem_id
            ORDER BY d.data"""
        ).fetchall()
    conn.close()
    return rows


def excluir_despesa(despesa_id: int):
    conn = conectar()
    conn.execute("DELETE FROM despesas WHERE id = ?", (despesa_id,))
    conn.commit()
    conn.close()


def criar_carga(**kwargs) -> int:
    conn = conectar()
    cur = conn.execute(
        """INSERT INTO cargas (viagem_id, empresa_cliente, tipo, data, valor, descricao)
        VALUES (:viagem_id, :empresa_cliente, :tipo, :data, :valor, :descricao)""",
        kwargs,
    )
    conn.commit()
    novo_id = cur.lastrowid
    conn.close()
    return novo_id


def listar_cargas(viagem_id: int = None):
    conn = conectar()
    if viagem_id:
        rows = conn.execute(
            "SELECT * FROM cargas WHERE viagem_id = ? ORDER BY data", (viagem_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT c.*, v.empresa_id, v.data_inicio
            FROM cargas c JOIN viagens v ON v.id = c.viagem_id
            ORDER BY c.data"""
        ).fetchall()
    conn.close()
    return rows


def excluir_carga(carga_id: int):
    conn = conectar()
    conn.execute("DELETE FROM cargas WHERE id = ?", (carga_id,))
    conn.commit()
    conn.close()


def listar_clientes_frete(empresa_id: int):
    """Nomes de empresas-cliente ja usados antes nas cargas dessa empresa
    (despesas_viagem), so pra sugestao/autocomplete -- nao e uma tabela
    normalizada, e so texto livre reaproveitado."""
    conn = conectar()
    rows = conn.execute(
        """SELECT DISTINCT c.empresa_cliente FROM cargas c
        JOIN viagens v ON v.id = c.viagem_id
        WHERE v.empresa_id = ? ORDER BY c.empresa_cliente""",
        (empresa_id,),
    ).fetchall()
    conn.close()
    return [r["empresa_cliente"] for r in rows]


def excluir_viagem(viagem_id: int):
    conn = conectar()
    conn.execute("DELETE FROM despesas WHERE viagem_id = ?", (viagem_id,))
    conn.execute("DELETE FROM cargas WHERE viagem_id = ?", (viagem_id,))
    conn.execute("DELETE FROM viagens WHERE id = ?", (viagem_id,))
    conn.commit()
    conn.close()

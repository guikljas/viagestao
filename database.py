"""Persistência, segurança de senha e isolamento por empresa."""

import os, re, sqlite3, hashlib, hmac, secrets
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "despesas.db")
DATABASE_URL = os.environ.get("DATABASE_URL", "")
USANDO_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))
CATEGORIAS = [
    "Combustível",
    "Pedágio",
    "Alimentação",
    "Hospedagem",
    "Estacionamento",
    "Manutenção",
    "Lavagem",
    "Transporte",
    "Outras",
]
STATUS_DESPESA = ["Rascunho", "Pendente", "Aprovada", "Reprovada", "Paga", "Cancelada"]
STATUS_VIAGEM = ["Planejada", "Em andamento", "Finalizada", "Cancelada"]
PERFIS = ["Administrador", "Usuário"]


class _ConexaoPostgres:
    def __init__(self):
        from psycopg import connect
        from psycopg.rows import dict_row

        self.raw = connect(DATABASE_URL, row_factory=dict_row)

    def execute(self, q, p=None):
        q = re.sub(r"(?<!:):([A-Za-z_][A-Za-z0-9_]*)", r"%(\1)s", q).replace("?", "%s")
        return self.raw.execute(q, p)

    def commit(self):
        self.raw.commit()

    def close(self):
        self.raw.close()


def conectar():
    if USANDO_POSTGRES:
        return _ConexaoPostgres()
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c


def _insert_id(q, p):
    c = conectar()
    if USANDO_POSTGRES:
        row = c.execute(q + " RETURNING id", p).fetchone()
        i = row["id"]
    else:
        i = c.execute(q, p).lastrowid
    c.commit()
    c.close()
    return i


def _hash(p, s=None):
    s = s or secrets.token_hex(16)
    return s + "$" + hashlib.pbkdf2_hmac("sha256", p.encode(), s.encode(), 310000).hex()


def verificar_senha(p, h):
    try:
        return hmac.compare_digest(_hash(p, h.split("$", 1)[0]), h)
    except (AttributeError, IndexError):
        return False


def _rows(q, p=()):
    c = conectar()
    r = c.execute(q, p).fetchall()
    c.close()
    return r


def _one(q, p=()):
    r = _rows(q, p)
    return r[0] if r else None


def inicializar():
    if USANDO_POSTGRES:
        _inicializar_postgres()
        return
    c = conectar()
    c.executescript("""
 CREATE TABLE IF NOT EXISTS empresas(id INTEGER PRIMARY KEY,nome TEXT UNIQUE NOT NULL,razao_social TEXT,cnpj TEXT,ativa INTEGER DEFAULT 1);
 CREATE TABLE IF NOT EXISTS usuarios(id INTEGER PRIMARY KEY,nome TEXT NOT NULL,email TEXT UNIQUE NOT NULL,senha_hash TEXT NOT NULL,perfil TEXT NOT NULL DEFAULT 'Usuário',ativo INTEGER DEFAULT 1,criado_em TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS usuario_empresas(usuario_id INTEGER REFERENCES usuarios(id),empresa_id INTEGER REFERENCES empresas(id),PRIMARY KEY(usuario_id,empresa_id));
 CREATE TABLE IF NOT EXISTS motoristas(id INTEGER PRIMARY KEY,nome TEXT NOT NULL,codigo TEXT,cpf TEXT,telefone TEXT,email TEXT,cnh TEXT,categoria_cnh TEXT,validade_cnh TEXT,status TEXT DEFAULT 'Ativo',observacoes TEXT,empresa_id INTEGER NOT NULL REFERENCES empresas(id));
 CREATE TABLE IF NOT EXISTS veiculos(id INTEGER PRIMARY KEY,placa TEXT NOT NULL,codigo TEXT,descricao TEXT,marca TEXT,ano INTEGER,tipo TEXT,quilometragem REAL DEFAULT 0,status TEXT DEFAULT 'Ativo',motorista_id INTEGER REFERENCES motoristas(id),empresa_id INTEGER NOT NULL REFERENCES empresas(id));
 CREATE TABLE IF NOT EXISTS viagens(id INTEGER PRIMARY KEY,empresa_id INTEGER NOT NULL REFERENCES empresas(id),motorista_id INTEGER NOT NULL REFERENCES motoristas(id),veiculo_id INTEGER NOT NULL REFERENCES veiculos(id),data_inicio TEXT NOT NULL,data_fim TEXT,origem TEXT,destino TEXT,motivo TEXT,cliente_atividade TEXT,hodometro_inicio REAL NOT NULL,hodometro_fim REAL,media_computador_bordo REAL,valor_adiantamento REAL DEFAULT 0,valor_devolvido REAL DEFAULT 0,valor_nf_ida REAL DEFAULT 0,valor_nf_retorno REAL DEFAULT 0,status TEXT DEFAULT 'Planejada',observacoes TEXT);
 CREATE TABLE IF NOT EXISTS despesas(id INTEGER PRIMARY KEY,viagem_id INTEGER NOT NULL REFERENCES viagens(id),categoria TEXT NOT NULL,data TEXT NOT NULL,valor REAL NOT NULL,litros REAL,local_abastecimento TEXT,forma_pagamento TEXT,descricao TEXT,estabelecimento TEXT,quilometragem REAL,status TEXT DEFAULT 'Pendente',motivo_reprovacao TEXT,criado_por INTEGER REFERENCES usuarios(id),criado_em TEXT DEFAULT CURRENT_TIMESTAMP);
 CREATE TABLE IF NOT EXISTS anexos_despesa(id INTEGER PRIMARY KEY,despesa_id INTEGER REFERENCES despesas(id),nome TEXT,caminho TEXT,tamanho INTEGER,usuario_id INTEGER,criado_em TEXT DEFAULT CURRENT_TIMESTAMP);
 CREATE TABLE IF NOT EXISTS pagamentos(id INTEGER PRIMARY KEY,despesa_id INTEGER UNIQUE REFERENCES despesas(id),data TEXT,valor REAL,forma_pagamento TEXT,responsavel_id INTEGER,observacao TEXT);
 CREATE TABLE IF NOT EXISTS cargas(id INTEGER PRIMARY KEY,viagem_id INTEGER NOT NULL REFERENCES viagens(id),empresa_cliente TEXT NOT NULL,tipo TEXT NOT NULL,data TEXT NOT NULL,valor REAL NOT NULL,descricao TEXT);
 CREATE TABLE IF NOT EXISTS categorias_despesa(id INTEGER PRIMARY KEY,empresa_id INTEGER REFERENCES empresas(id),nome TEXT NOT NULL,ativo INTEGER DEFAULT 1,UNIQUE(empresa_id,nome));
 CREATE TABLE IF NOT EXISTS auditoria(id INTEGER PRIMARY KEY,usuario_id INTEGER,empresa_id INTEGER,acao TEXT,entidade TEXT,registro_id INTEGER,criado_em TEXT DEFAULT CURRENT_TIMESTAMP);
 CREATE INDEX IF NOT EXISTS idx_viagens_empresa ON viagens(empresa_id);CREATE INDEX IF NOT EXISTS idx_despesas_viagem ON despesas(viagem_id);
 """)
    # Acrescenta colunas a instalações antigas sem apagar dados.
    mig = {
        "empresas": {
            "razao_social": "TEXT",
            "cnpj": "TEXT",
            "ativa": "INTEGER DEFAULT 1",
        },
        "motoristas": {
            "cpf": "TEXT",
            "telefone": "TEXT",
            "email": "TEXT",
            "cnh": "TEXT",
            "categoria_cnh": "TEXT",
            "validade_cnh": "TEXT",
            "status": "TEXT DEFAULT 'Ativo'",
            "observacoes": "TEXT",
        },
        "veiculos": {
            "marca": "TEXT",
            "ano": "INTEGER",
            "tipo": "TEXT",
            "quilometragem": "REAL DEFAULT 0",
            "status": "TEXT DEFAULT 'Ativo'",
            "motorista_id": "INTEGER",
        },
        "viagens": {
            "motivo": "TEXT",
            "cliente_atividade": "TEXT",
            "status": "TEXT DEFAULT 'Planejada'",
        },
        "despesas": {
            "estabelecimento": "TEXT",
            "quilometragem": "REAL",
            "status": "TEXT DEFAULT 'Pendente'",
            "motivo_reprovacao": "TEXT",
            "criado_por": "INTEGER",
            "criado_em": "TEXT",
        },
    }
    for t, cols in mig.items():
        old = {x[1] for x in c.execute(f"PRAGMA table_info({t})")}
        for n, k in cols.items():
            if n not in old:
                c.execute(f"ALTER TABLE {t} ADD COLUMN {n} {k}")
    c.execute(
        "UPDATE empresas SET nome='ERIMAX',razao_social='Erimar Indústria e Comércio de Produtos para Saúde Ltda.',cnpj='11.463.608/0001-79' WHERE nome='ERIMAR'"
    )
    c.execute(
        "UPDATE empresas SET razao_social='Comercial Mark Atacadista Ltda.',cnpj='09.315.996/0001-07' WHERE nome='MARK'"
    )
    c.execute(
        "UPDATE empresas SET razao_social='Erimar Indústria e Comércio de Produtos para Saúde Ltda.',cnpj='11.463.608/0001-79' WHERE nome='ERIMAX'"
    )
    for n, rj, cnpj in [
        ("MARK", "Comercial Mark Atacadista Ltda.", "09.315.996/0001-07"),
        (
            "ERIMAX",
            "Erimar Indústria e Comércio de Produtos para Saúde Ltda.",
            "11.463.608/0001-79",
        ),
    ]:
        c.execute(
            "INSERT OR IGNORE INTO empresas(nome,razao_social,cnpj) VALUES(?,?,?)",
            (n, rj, cnpj),
        )
    for n in CATEGORIAS:
        c.execute(
            "INSERT OR IGNORE INTO categorias_despesa(empresa_id,nome) VALUES(NULL,?)",
            (n,),
        )
    if not c.execute(
        "SELECT 1 FROM usuarios WHERE email='admin@viagens.local'"
    ).fetchone():
        u = c.execute(
            "INSERT INTO usuarios(nome,email,senha_hash,perfil,criado_em) VALUES(?,?,?,?,?)",
            (
                "Administrador",
                "admin@viagens.local",
                _hash("admin123"),
                "Administrador",
                datetime.now().isoformat(),
            ),
        ).lastrowid
        for e in c.execute("SELECT id FROM empresas"):
            c.execute("INSERT INTO usuario_empresas VALUES(?,?)", (u, e[0]))
    c.execute("UPDATE usuarios SET perfil='Usuário' WHERE perfil NOT IN (?, ?)", PERFIS)
    c.commit()
    c.close()


def _inicializar_postgres():
    """Schema limpo para Neon/PostgreSQL; dados locais são enviados pelo script de migração."""
    schema = """
 CREATE TABLE IF NOT EXISTS empresas(id BIGSERIAL PRIMARY KEY,nome TEXT UNIQUE NOT NULL,razao_social TEXT,cnpj TEXT,ativa INTEGER DEFAULT 1);
 CREATE TABLE IF NOT EXISTS usuarios(id BIGSERIAL PRIMARY KEY,nome TEXT NOT NULL,email TEXT UNIQUE NOT NULL,senha_hash TEXT NOT NULL,perfil TEXT NOT NULL DEFAULT 'Usuário',ativo INTEGER DEFAULT 1,criado_em TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS usuario_empresas(usuario_id BIGINT REFERENCES usuarios(id),empresa_id BIGINT REFERENCES empresas(id),PRIMARY KEY(usuario_id,empresa_id));
 CREATE TABLE IF NOT EXISTS motoristas(id BIGSERIAL PRIMARY KEY,nome TEXT NOT NULL,codigo TEXT,cpf TEXT,telefone TEXT,email TEXT,cnh TEXT,categoria_cnh TEXT,validade_cnh TEXT,status TEXT DEFAULT 'Ativo',observacoes TEXT,empresa_id BIGINT NOT NULL REFERENCES empresas(id));
 CREATE TABLE IF NOT EXISTS veiculos(id BIGSERIAL PRIMARY KEY,placa TEXT NOT NULL,codigo TEXT,descricao TEXT,marca TEXT,ano INTEGER,tipo TEXT,quilometragem DOUBLE PRECISION DEFAULT 0,status TEXT DEFAULT 'Ativo',motorista_id BIGINT REFERENCES motoristas(id),empresa_id BIGINT NOT NULL REFERENCES empresas(id));
 CREATE TABLE IF NOT EXISTS viagens(id BIGSERIAL PRIMARY KEY,empresa_id BIGINT NOT NULL REFERENCES empresas(id),motorista_id BIGINT NOT NULL REFERENCES motoristas(id),veiculo_id BIGINT NOT NULL REFERENCES veiculos(id),data_inicio TEXT NOT NULL,data_fim TEXT,origem TEXT,destino TEXT,motivo TEXT,cliente_atividade TEXT,hodometro_inicio DOUBLE PRECISION NOT NULL,hodometro_fim DOUBLE PRECISION,media_computador_bordo DOUBLE PRECISION,valor_adiantamento DOUBLE PRECISION DEFAULT 0,valor_devolvido DOUBLE PRECISION DEFAULT 0,valor_nf_ida DOUBLE PRECISION DEFAULT 0,valor_nf_retorno DOUBLE PRECISION DEFAULT 0,status TEXT DEFAULT 'Planejada',observacoes TEXT);
 CREATE TABLE IF NOT EXISTS despesas(id BIGSERIAL PRIMARY KEY,viagem_id BIGINT NOT NULL REFERENCES viagens(id),categoria TEXT NOT NULL,data TEXT NOT NULL,valor DOUBLE PRECISION NOT NULL,litros DOUBLE PRECISION,local_abastecimento TEXT,forma_pagamento TEXT,descricao TEXT,estabelecimento TEXT,quilometragem DOUBLE PRECISION,status TEXT DEFAULT 'Pendente',motivo_reprovacao TEXT,criado_por BIGINT REFERENCES usuarios(id),criado_em TEXT DEFAULT CURRENT_TIMESTAMP::text);
 CREATE TABLE IF NOT EXISTS anexos_despesa(id BIGSERIAL PRIMARY KEY,despesa_id BIGINT REFERENCES despesas(id),nome TEXT,caminho TEXT,tamanho BIGINT,usuario_id BIGINT,criado_em TEXT DEFAULT CURRENT_TIMESTAMP::text);
 CREATE TABLE IF NOT EXISTS pagamentos(id BIGSERIAL PRIMARY KEY,despesa_id BIGINT UNIQUE REFERENCES despesas(id),data TEXT,valor DOUBLE PRECISION,forma_pagamento TEXT,responsavel_id BIGINT,observacao TEXT);
 CREATE TABLE IF NOT EXISTS categorias_despesa(id BIGSERIAL PRIMARY KEY,empresa_id BIGINT REFERENCES empresas(id),nome TEXT NOT NULL,ativo INTEGER DEFAULT 1);
 CREATE TABLE IF NOT EXISTS auditoria(id BIGSERIAL PRIMARY KEY,usuario_id BIGINT,empresa_id BIGINT,acao TEXT,entidade TEXT,registro_id BIGINT,criado_em TEXT DEFAULT CURRENT_TIMESTAMP::text);
 CREATE TABLE IF NOT EXISTS cargas(id BIGSERIAL PRIMARY KEY,viagem_id BIGINT NOT NULL REFERENCES viagens(id),empresa_cliente TEXT NOT NULL,tipo TEXT NOT NULL,data TEXT NOT NULL,valor DOUBLE PRECISION NOT NULL,descricao TEXT);
 CREATE INDEX IF NOT EXISTS idx_viagens_empresa ON viagens(empresa_id);CREATE INDEX IF NOT EXISTS idx_despesas_viagem ON despesas(viagem_id);
 """
    c = conectar()
    for s in schema.split(";"):
        if s.strip():
            c.execute(s)
    for n, rj, cnpj in [
        ("MARK", "Comercial Mark Atacadista Ltda.", "09.315.996/0001-07"),
        (
            "ERIMAX",
            "Erimar Indústria e Comércio de Produtos para Saúde Ltda.",
            "11.463.608/0001-79",
        ),
    ]:
        c.execute(
            "INSERT INTO empresas(nome,razao_social,cnpj) VALUES(%s,%s,%s) ON CONFLICT (nome) DO NOTHING",
            (n, rj, cnpj),
        )
    for n in CATEGORIAS:
        if not c.execute(
            "SELECT 1 FROM categorias_despesa WHERE empresa_id IS NULL AND nome=%s",
            (n,),
        ).fetchone():
            c.execute(
                "INSERT INTO categorias_despesa(empresa_id,nome) VALUES(NULL,%s)", (n,)
            )
    if not c.execute(
        "SELECT 1 FROM usuarios WHERE email=%s", ("admin@viagens.local",)
    ).fetchone():
        u = c.execute(
            "INSERT INTO usuarios(nome,email,senha_hash,perfil,criado_em) VALUES(%s,%s,%s,%s,%s) RETURNING id",
            (
                "Administrador",
                "admin@viagens.local",
                _hash("admin123"),
                "Administrador",
                datetime.now().isoformat(),
            ),
        ).fetchone()["id"]
        for e in c.execute("SELECT id FROM empresas").fetchall():
            c.execute("INSERT INTO usuario_empresas VALUES(%s,%s)", (u, e["id"]))
    c.execute(
        "UPDATE usuarios SET perfil='Usuário' WHERE perfil NOT IN (%s, %s)", PERFIS
    )
    c.commit()
    c.close()


def autenticar(email, senha):
    u = _one(
        "SELECT * FROM usuarios WHERE lower(email)=lower(?) AND ativo=1",
        (email.strip(),),
    )
    return u if u and verificar_senha(senha, u["senha_hash"]) else None


def listar_empresas(usuario_id=None):
    q = "SELECT * FROM empresas WHERE ativa=1"
    p = []
    if usuario_id:
        q += " AND id IN(SELECT empresa_id FROM usuario_empresas WHERE usuario_id=?)"
        p = [usuario_id]
    return _rows(q + " ORDER BY nome", p)


def usuario_tem_empresa(u, e):
    return bool(
        _one(
            "SELECT 1 FROM usuario_empresas WHERE usuario_id=? AND empresa_id=?", (u, e)
        )
    )


def listar_usuarios():
    agregador = (
        "string_agg(e.nome, ', ')" if USANDO_POSTGRES else "group_concat(e.nome,', ')"
    )
    return _rows(
        f"SELECT u.*,{agregador} empresas FROM usuarios u "
        "LEFT JOIN usuario_empresas ue ON ue.usuario_id=u.id "
        "LEFT JOIN empresas e ON e.id=ue.empresa_id "
        "GROUP BY u.id ORDER BY u.nome"
    )


def obter_usuario(usuario_id):
    return _one("SELECT * FROM usuarios WHERE id=?", (usuario_id,))


def empresas_do_usuario(usuario_id):
    return _rows(
        "SELECT empresa_id FROM usuario_empresas WHERE usuario_id=? ORDER BY empresa_id",
        (usuario_id,),
    )


def criar_usuario(nome, email, senha, perfil, empresas):
    if perfil not in PERFIS:
        raise ValueError("Perfil de usuário inválido.")
    if not empresas:
        raise ValueError("Selecione ao menos uma empresa para o usuário.")
    c = conectar()
    q = "INSERT INTO usuarios(nome,email,senha_hash,perfil,criado_em) VALUES(?,?,?,?,?)"
    cur = c.execute(
        q + (" RETURNING id" if USANDO_POSTGRES else ""),
        (nome, email.lower(), _hash(senha), perfil, datetime.now().isoformat()),
    )
    i = cur.fetchone()["id"] if USANDO_POSTGRES else cur.lastrowid
    for e in empresas:
        c.execute("INSERT INTO usuario_empresas VALUES(?,?)", (i, e))
    c.commit()
    c.close()
    return i


def atualizar_usuario(usuario_id, nome, email, perfil, ativo, empresas, senha=None):
    """Atualiza dados e acessos sem alterar a senha quando ela estiver vazia."""
    if perfil not in PERFIS:
        raise ValueError("Perfil de usuário inválido.")
    if not empresas:
        raise ValueError("Selecione ao menos uma empresa para o usuário.")

    c = conectar()
    try:
        parametros = {
            "id": usuario_id,
            "nome": nome.strip(),
            "email": email.strip().lower(),
            "perfil": perfil,
            "ativo": int(bool(ativo)),
        }
        sql = (
            "UPDATE usuarios SET nome=:nome,email=:email,perfil=:perfil,ativo=:ativo "
            "WHERE id=:id"
        )
        if senha:
            parametros["senha_hash"] = _hash(senha)
            sql = (
                "UPDATE usuarios SET nome=:nome,email=:email,perfil=:perfil,ativo=:ativo,"
                "senha_hash=:senha_hash WHERE id=:id"
            )
        c.execute(sql, parametros)
        c.execute("DELETE FROM usuario_empresas WHERE usuario_id=?", (usuario_id,))
        for empresa_id in empresas:
            c.execute(
                "INSERT INTO usuario_empresas(usuario_id,empresa_id) VALUES(?,?)",
                (usuario_id, empresa_id),
            )
        c.commit()
    except Exception:
        c.raw.rollback() if USANDO_POSTGRES else c.rollback()
        raise
    finally:
        c.close()


def possui_outro_administrador(usuario_id):
    return bool(
        _one(
            "SELECT 1 FROM usuarios WHERE perfil='Administrador' AND ativo=1 AND id<>?",
            (usuario_id,),
        )
    )


def alterar_senha(i, senha):
    c = conectar()
    c.execute("UPDATE usuarios SET senha_hash=? WHERE id=?", (_hash(senha), i))
    c.commit()
    c.close()


def auditar(u, e, a, ent, r=None):
    c = conectar()
    c.execute(
        "INSERT INTO auditoria(usuario_id,empresa_id,acao,entidade,registro_id) VALUES(?,?,?,?,?)",
        (u, e, a, ent, r),
    )
    c.commit()
    c.close()


def listar_motoristas(e):
    return _rows("SELECT * FROM motoristas WHERE empresa_id=? ORDER BY nome", (e,))


def criar_motorista(**d):
    return _insert_id(
        "INSERT INTO motoristas(nome,codigo,cpf,telefone,email,cnh,categoria_cnh,validade_cnh,status,observacoes,empresa_id) VALUES(:nome,:codigo,:cpf,:telefone,:email,:cnh,:categoria_cnh,:validade_cnh,:status,:observacoes,:empresa_id)",
        d,
    )


def listar_veiculos(e):
    return _rows(
        "SELECT v.*,m.nome motorista_nome FROM veiculos v LEFT JOIN motoristas m ON m.id=v.motorista_id WHERE v.empresa_id=? ORDER BY placa",
        (e,),
    )


def criar_veiculo(**d):
    return _insert_id(
        "INSERT INTO veiculos(placa,codigo,descricao,marca,ano,tipo,quilometragem,status,motorista_id,empresa_id) VALUES(:placa,:codigo,:descricao,:marca,:ano,:tipo,:quilometragem,:status,:motorista_id,:empresa_id)",
        d,
    )


def criar_viagem(**d):
    for k, v in {
        "motivo": None,
        "cliente_atividade": None,
        "status": "Planejada",
        "valor_adiantamento": 0,
        "valor_devolvido": 0,
        "valor_nf_ida": 0,
        "valor_nf_retorno": 0,
    }.items():
        d.setdefault(k, v)
    return _insert_id(
        "INSERT INTO viagens(empresa_id,motorista_id,veiculo_id,data_inicio,data_fim,origem,destino,motivo,cliente_atividade,hodometro_inicio,hodometro_fim,media_computador_bordo,valor_adiantamento,valor_devolvido,valor_nf_ida,valor_nf_retorno,status,observacoes) VALUES(:empresa_id,:motorista_id,:veiculo_id,:data_inicio,:data_fim,:origem,:destino,:motivo,:cliente_atividade,:hodometro_inicio,:hodometro_fim,:media_computador_bordo,:valor_adiantamento,:valor_devolvido,:valor_nf_ida,:valor_nf_retorno,:status,:observacoes)",
        d,
    )


def atualizar_viagem(i, **d):
    c = conectar()
    c.execute(
        "UPDATE viagens SET data_fim=:data_fim,hodometro_fim=:hodometro_fim,media_computador_bordo=:media_computador_bordo,valor_devolvido=:valor_devolvido,status=:status,observacoes=:observacoes WHERE id=:id",
        dict(d, id=i),
    )
    c.commit()
    c.close()


def atualizar_dados_basicos_viagem(i, **d):
    """Atualiza os dados de abertura sem misturar com o fechamento da viagem."""
    c = conectar()
    c.execute(
        "UPDATE viagens SET motorista_id=:motorista_id,veiculo_id=:veiculo_id,data_inicio=:data_inicio,origem=:origem,destino=:destino,motivo=:motivo,cliente_atividade=:cliente_atividade,hodometro_inicio=:hodometro_inicio,valor_adiantamento=:valor_adiantamento,observacoes=:observacoes WHERE id=:id",
        dict(d, id=i),
    )
    c.commit()
    c.close()


def excluir_viagem(i):
    """Remove uma viagem e seus lançamentos dependentes de forma transacional."""
    c = conectar()
    try:
        c.execute(
            "DELETE FROM pagamentos WHERE despesa_id IN (SELECT id FROM despesas WHERE viagem_id=?)",
            (i,),
        )
        c.execute(
            "DELETE FROM anexos_despesa WHERE despesa_id IN (SELECT id FROM despesas WHERE viagem_id=?)",
            (i,),
        )
        c.execute("DELETE FROM despesas WHERE viagem_id=?", (i,))
        c.execute("DELETE FROM cargas WHERE viagem_id=?", (i,))
        c.execute("DELETE FROM viagens WHERE id=?", (i,))
        c.commit()
    except Exception:
        c.raw.rollback() if USANDO_POSTGRES else c.rollback()
        raise
    finally:
        c.close()


def listar_viagens(e=None, empresa_id=None):
    e = empresa_id if empresa_id is not None else e
    q = "SELECT v.*,em.nome empresa_nome,m.nome motorista_nome,m.codigo motorista_codigo,ve.placa veiculo_placa,ve.codigo veiculo_codigo FROM viagens v JOIN empresas em ON em.id=v.empresa_id JOIN motoristas m ON m.id=v.motorista_id JOIN veiculos ve ON ve.id=v.veiculo_id"
    return _rows(
        q + (" WHERE v.empresa_id=?" if e else "") + " ORDER BY v.data_inicio DESC",
        (e,) if e else (),
    )


def obter_viagem(i):
    return _one(
        "SELECT v.*,m.nome motorista_nome,ve.placa veiculo_placa FROM viagens v JOIN motoristas m ON m.id=v.motorista_id JOIN veiculos ve ON ve.id=v.veiculo_id WHERE v.id=?",
        (i,),
    )


def criar_despesa(**d):
    for k, v in {
        "estabelecimento": None,
        "quilometragem": None,
        "status": "Pendente",
        "criado_por": None,
        "litros": None,
        "forma_pagamento": None,
        "local_abastecimento": None,
    }.items():
        d.setdefault(k, v)
    return _insert_id(
        "INSERT INTO despesas(viagem_id,categoria,data,valor,litros,local_abastecimento,forma_pagamento,descricao,estabelecimento,quilometragem,status,criado_por) VALUES(:viagem_id,:categoria,:data,:valor,:litros,:local_abastecimento,:forma_pagamento,:descricao,:estabelecimento,:quilometragem,:status,:criado_por)",
        d,
    )


def listar_despesas(viagem_id=None, empresa_id=None, status=None):
    q = "SELECT d.*,v.empresa_id,v.id viagem_numero,m.nome motorista_nome,e.nome empresa_nome FROM despesas d JOIN viagens v ON v.id=d.viagem_id JOIN motoristas m ON m.id=v.motorista_id JOIN empresas e ON e.id=v.empresa_id WHERE 1=1"
    p = []
    if viagem_id:
        q += " AND d.viagem_id=?"
        p.append(viagem_id)
    if empresa_id:
        q += " AND v.empresa_id=?"
        p.append(empresa_id)
    if status:
        q += " AND d.status=?"
        p.append(status)
    return _rows(q + " ORDER BY d.data DESC", p)


def listar_despesas_periodo(empresa_id, inicio, fim):
    q = "SELECT d.*,v.empresa_id,v.id viagem_numero,m.nome motorista_nome,e.nome empresa_nome FROM despesas d JOIN viagens v ON v.id=d.viagem_id JOIN motoristas m ON m.id=v.motorista_id JOIN empresas e ON e.id=v.empresa_id WHERE v.empresa_id=? AND d.data>=? AND d.data<? ORDER BY d.data DESC"
    return _rows(q, (empresa_id, inicio, fim))


def alterar_status_despesa(i, s, m=None):
    c = conectar()
    c.execute("UPDATE despesas SET status=?,motivo_reprovacao=? WHERE id=?", (s, m, i))
    c.commit()
    c.close()


def anexar_comprovante(despesa_id, nome, caminho, tamanho, usuario_id):
    c = conectar()
    c.execute(
        "INSERT INTO anexos_despesa(despesa_id,nome,caminho,tamanho,usuario_id) VALUES(?,?,?,?,?)",
        (despesa_id, nome, caminho, tamanho, usuario_id),
    )
    c.commit()
    c.close()


def listar_anexos(despesa_id):
    return _rows(
        "SELECT * FROM anexos_despesa WHERE despesa_id=? ORDER BY criado_em DESC",
        (despesa_id,),
    )


def registrar_pagamento(i, data, valor, forma, u, obs):
    if not _one("SELECT 1 FROM despesas WHERE id=? AND status='Aprovada'", (i,)):
        raise ValueError("Somente despesas aprovadas podem ser pagas.")
    c = conectar()
    c.execute(
        "INSERT INTO pagamentos(despesa_id,data,valor,forma_pagamento,responsavel_id,observacao) VALUES(?,?,?,?,?,?)",
        (i, data, valor, forma, u, obs),
    )
    c.execute("UPDATE despesas SET status='Paga' WHERE id=?", (i,))
    c.commit()
    c.close()


def resumo_dashboard(e):
    ds = listar_despesas(empresa_id=e)
    vs = listar_viagens(e)
    ms = listar_motoristas(e)
    valor_por_status = lambda status: sum(
        float(item["valor"]) for item in ds if item["status"] == status
    )
    total_aprovado = valor_por_status("Aprovada") + valor_por_status("Paga")
    total_lancado = sum(
        float(item["valor"])
        for item in ds
        if item["status"] not in ("Reprovada", "Cancelada")
    )
    return dict(
        total=total_lancado,
        pendente=valor_por_status("Pendente"),
        aprovada=total_aprovado,
        reprovada=valor_por_status("Reprovada"),
        viagens=len(vs),
        motoristas=len([m for m in ms if m["status"] == "Ativo"]),
        media_viagem=total_lancado / len(vs) if vs else 0,
        media_motorista=total_lancado / len(ms) if ms else 0,
        despesas=ds,
    )


def excluir_motorista(i):
    if _one("SELECT 1 FROM viagens WHERE motorista_id=?", (i,)):
        raise ValueError(
            "Este motorista possui viagens registradas; marque-o como inativo para preservar o histórico."
        )
    c = conectar()
    c.execute("DELETE FROM motoristas WHERE id=?", (i,))
    c.commit()
    c.close()


def excluir_veiculo(i):
    if _one("SELECT 1 FROM viagens WHERE veiculo_id=?", (i,)):
        raise ValueError(
            "Este veículo possui viagens registradas; marque-o como inativo para preservar o histórico."
        )
    c = conectar()
    c.execute("DELETE FROM veiculos WHERE id=?", (i,))
    c.commit()
    c.close()


def atualizar_motorista(i, **d):
    c = conectar()
    c.execute(
        "UPDATE motoristas SET nome=:nome,codigo=:codigo,cpf=:cpf,telefone=:telefone,email=:email,cnh=:cnh,categoria_cnh=:categoria_cnh,validade_cnh=:validade_cnh,status=:status,observacoes=:observacoes WHERE id=:id",
        dict(d, id=i),
    )
    c.commit()
    c.close()


def atualizar_veiculo(i, **d):
    c = conectar()
    c.execute(
        "UPDATE veiculos SET placa=:placa,codigo=:codigo,marca=:marca,descricao=:descricao,ano=:ano,tipo=:tipo,quilometragem=:quilometragem,motorista_id=:motorista_id,status=:status WHERE id=:id",
        dict(d, id=i),
    )
    c.commit()
    c.close()


def excluir_usuario(i):
    c = conectar()
    c.execute("DELETE FROM usuario_empresas WHERE usuario_id=?", (i,))
    c.execute("DELETE FROM usuarios WHERE id=?", (i,))
    c.commit()
    c.close()


def listar_cargas(viagem_id=None):
    return _rows(
        "SELECT * FROM cargas"
        + (" WHERE viagem_id=?" if viagem_id else "")
        + " ORDER BY data",
        (viagem_id,) if viagem_id else (),
    )


def listar_cargas_empresa(empresa_id):
    return _rows(
        "SELECT c.* FROM cargas c JOIN viagens v ON v.id=c.viagem_id "
        "WHERE v.empresa_id=? ORDER BY c.data DESC",
        (empresa_id,),
    )


def listar_cargas_periodo(empresa_id, inicio, fim):
    return _rows(
        "SELECT c.* FROM cargas c JOIN viagens v ON v.id=c.viagem_id WHERE v.empresa_id=? AND c.data>=? AND c.data<? ORDER BY c.data",
        (empresa_id, inicio, fim),
    )


def criar_carga(**d):
    return _insert_id(
        "INSERT INTO cargas(viagem_id,empresa_cliente,tipo,data,valor,descricao) VALUES(:viagem_id,:empresa_cliente,:tipo,:data,:valor,:descricao)",
        d,
    )


def excluir_carga(i):
    c = conectar()
    c.execute("DELETE FROM cargas WHERE id=?", (i,))
    c.commit()
    c.close()


def excluir_despesa(i):
    c = conectar()
    c.execute("DELETE FROM despesas WHERE id=?", (i,))
    c.commit()
    c.close()

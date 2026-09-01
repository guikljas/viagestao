"""Importa o histórico legado sem duplicar viagens e unifica motoristas.

Uso (PowerShell, com DATABASE_URL do Neon já definida):
  python importar_historico_zip.py "C:/Users/user/Downloads/despesas_viagem.zip"
Antes de gravar, confira com:
  python importar_historico_zip.py "C:/Users/user/Downloads/despesas_viagem.zip" --dry-run
"""
import argparse
import os
import sqlite3
import tempfile
import unicodedata
import zipfile

import database as db


# Variações encontradas no banco legado que representam a mesma pessoa.
ALIASES = {
    "MARK": {
        "IZAIAS MENEZES DA SILVA": "IZAIAS MENEZES DA SILVA",
        "JOVENTINO": "JOVENTINO FRANCISCO SANTOS",
        "JOVENTINO FRANCISCO SANTOS": "JOVENTINO FRANCISCO SANTOS",
        "LUCAS": "LUCAS FERREIRA DOS SANTOS",
        "LUCAS FERREIRA": "LUCAS FERREIRA DOS SANTOS",
        "LUCAS FERREIRA DOS SANTOS": "LUCAS FERREIRA DOS SANTOS",
        "MICHAEL": "MICHAEL RAFAEL PESSOA DOS SANTOS",
        "MICHAEL RAFAEL PESSOA DOS SANTOS": "MICHAEL RAFAEL PESSOA DOS SANTOS",
    },
    "ERIMAX": {
        "ANDERSON": "ANDERSON ANTONIO FELIZARDO DE SOUZA",
        "ANDERSON ANTONIO FELIZARDO DE SOUZA": "ANDERSON ANTONIO FELIZARDO DE SOUZA",
        "IZAIAS MENEZES DA SILVA": "IZAIAS MENEZES DA SILVA",
        "LUCAS": "LUCAS FERREIRA DOS SANTOS",
        "LUCAS FERREIRA": "LUCAS FERREIRA DOS SANTOS",
        "LUCAS FERREIRA DOS SANTOS": "LUCAS FERREIRA DOS SANTOS",
        "MAYKON PEREIRA": "MAYKON RODRIGO PEREIRA",
        "MAYKON RODRIGO PEREIRA": "MAYKON RODRIGO PEREIRA",
        "NILTON": "NILTON PAZ",
        "NILTON PAZ": "NILTON PAZ",
        "THIAGO": "TIAGO CUSTODIO MARTINS",
        "TIAGO CUSTODIO": "TIAGO CUSTODIO MARTINS",
        "TIAGO CUSTODIO MARTINS": "TIAGO CUSTODIO MARTINS",
    },
}


def texto_chave(valor):
    valor = unicodedata.normalize("NFKD", valor or "").encode("ascii", "ignore").decode("ascii")
    valor = valor.upper().replace("(MANUTENCAO)", "")
    return " ".join("".join(c if c.isalnum() or c == " " else " " for c in valor).split())


def nome_padrao(empresa, nome):
    chave = texto_chave(nome)
    return ALIASES.get(empresa, {}).get(chave, chave)


def placa_chave(placa):
    return "".join(c for c in (placa or "").upper() if c.isalnum())


def consolidar_veiculos(empresa_id, gravar):
    """Unifica placas equivalentes e preserva todas as viagens vinculadas."""
    grupos = {}
    for veiculo in db.listar_veiculos(empresa_id):
        grupos.setdefault(placa_chave(veiculo["placa"]), []).append(veiculo)
    con = db.conectar()
    try:
        viagens = db.listar_viagens(empresa_id)
        for placa, itens in grupos.items():
            itens.sort(key=lambda item: (-len([v for v in viagens if v["veiculo_id"] == item["id"]]), item["id"]))
            principal = itens[0]
            motorista_principal = principal["motorista_id"]
            if gravar:
                con.execute("UPDATE veiculos SET placa=? WHERE id=?", (placa, principal["id"]))
            for duplicado in itens[1:]:
                if gravar:
                    if motorista_principal is None and duplicado["motorista_id"] is not None:
                        con.execute("UPDATE veiculos SET motorista_id=? WHERE id=?", (duplicado["motorista_id"], principal["id"]))
                        motorista_principal = duplicado["motorista_id"]
                    con.execute("UPDATE viagens SET veiculo_id=? WHERE veiculo_id=?", (principal["id"], duplicado["id"]))
                    con.execute("DELETE FROM veiculos WHERE id=?", (duplicado["id"],))
        if gravar:
            con.commit()
    finally:
        con.close()


def definir_codigos_veiculos(empresa_id, empresa, gravar):
    prefixo = "MKV" if empresa == "MARK" else "ERXV"
    veiculos = sorted(db.listar_veiculos(empresa_id), key=lambda item: placa_chave(item["placa"]))
    if gravar:
        con = db.conectar()
        try:
            for posicao, veiculo in enumerate(veiculos, 1):
                con.execute("UPDATE veiculos SET codigo=? WHERE id=?", (f"{prefixo}-{posicao:03d}", veiculo["id"]))
            con.commit()
        finally:
            con.close()
    return len(veiculos)


def valor(row, campo, padrao=None):
    return row[campo] if campo in row.keys() else padrao


def assinatura_viagem(empresa_id, motorista_id, veiculo_id, row):
    return (empresa_id, motorista_id, veiculo_id, valor(row, "data_inicio"), valor(row, "data_fim"),
            (valor(row, "origem") or "").strip().upper(), (valor(row, "destino") or "").strip().upper(),
            float(valor(row, "hodometro_inicio", 0) or 0))


def obter_id_empresa(nome):
    nome = "ERIMAX" if nome == "ERIMAR" else nome
    item = next((x for x in db.listar_empresas() if x["nome"] == nome), None)
    if not item:
        raise RuntimeError(f"Empresa {nome} não existe no banco de destino.")
    return item["id"], nome


def consolidar_motoristas(empresa_id, empresa, gravar):
    """Unifica registros já existentes e redireciona todas as referências."""
    grupos = {}
    for motorista in db.listar_motoristas(empresa_id):
        grupos.setdefault(nome_padrao(empresa, motorista["nome"]), []).append(motorista)
    mapa = {}
    con = db.conectar()
    try:
        for nome, itens in grupos.items():
            # Conserva o registro mais utilizado nas viagens; isso preserva os dados associados.
            itens.sort(key=lambda x: (-len([v for v in db.listar_viagens(empresa_id) if v["motorista_id"] == x["id"]]), x["id"]))
            principal = itens[0]
            mapa[nome] = principal["id"]
            if gravar:
                con.execute("UPDATE motoristas SET nome=? WHERE id=?", (nome, principal["id"]))
            for duplicado in itens[1:]:
                if gravar:
                    con.execute("UPDATE viagens SET motorista_id=? WHERE motorista_id=?", (principal["id"], duplicado["id"]))
                    con.execute("UPDATE veiculos SET motorista_id=? WHERE motorista_id=?", (principal["id"], duplicado["id"]))
                    con.execute("DELETE FROM motoristas WHERE id=?", (duplicado["id"],))
        if gravar:
            con.commit()
    finally:
        con.close()
    return mapa


def motorista_destino(mapa, empresa_id, empresa, origem, gravar):
    nome = nome_padrao(empresa, origem["nome"])
    if nome in mapa:
        return mapa[nome]
    if not gravar:
        return -len(mapa) - 1
    ident = db.criar_motorista(
        nome=nome, codigo=None, cpf=valor(origem, "cpf"), telefone=valor(origem, "telefone"),
        email=valor(origem, "email"), cnh=valor(origem, "cnh"), categoria_cnh=valor(origem, "categoria_cnh"),
        validade_cnh=valor(origem, "validade_cnh"), status=valor(origem, "status", "Ativo") or "Ativo",
        observacoes=valor(origem, "observacoes"), empresa_id=empresa_id,
    )
    mapa[nome] = ident
    return ident


def veiculo_destino(mapa, empresa_id, origem, motorista_id, gravar):
    chave = placa_chave(origem["placa"])
    if chave in mapa:
        return mapa[chave]
    if not gravar:
        return -len(mapa) - 1
    ident = db.criar_veiculo(
        placa=chave, codigo=valor(origem, "codigo"), descricao=valor(origem, "descricao"),
        marca=valor(origem, "marca"), ano=valor(origem, "ano"), tipo=valor(origem, "tipo"),
        quilometragem=valor(origem, "quilometragem", 0) or 0, status=valor(origem, "status", "Ativo") or "Ativo",
        motorista_id=motorista_id, empresa_id=empresa_id,
    )
    mapa[chave] = ident
    return ident


def definir_codigos(empresa_id, empresa, gravar):
    prefixo = "MK" if empresa == "MARK" else "ERX"
    motoristas = sorted(db.listar_motoristas(empresa_id), key=lambda x: texto_chave(x["nome"]))
    if gravar:
        con = db.conectar()
        try:
            for posicao, motorista in enumerate(motoristas, 1):
                con.execute("UPDATE motoristas SET codigo=? WHERE id=?", (f"{prefixo}-{posicao:03d}", motorista["id"]))
            con.commit()
        finally:
            con.close()
    return len(motoristas)


def importar(arquivo_zip, gravar):
    with zipfile.ZipFile(arquivo_zip) as pacote, tempfile.TemporaryDirectory() as pasta:
        membro = next((n for n in pacote.namelist() if n.endswith("/despesas.db")), None)
        if not membro:
            raise RuntimeError("O ZIP não possui o arquivo despesas.db esperado.")
        origem_db = os.path.join(pasta, "origem.db")
        with open(origem_db, "wb") as saida:
            saida.write(pacote.read(membro))
        origem = sqlite3.connect(origem_db)
        origem.row_factory = sqlite3.Row
        try:
            db.inicializar()
            empresas_origem = {x["id"]: x["nome"] for x in origem.execute("SELECT id,nome FROM empresas")}
            resumo = {"viagens_importadas": 0, "viagens_existentes": 0, "despesas": 0, "cargas": 0}
            for origem_empresa_id, origem_empresa in empresas_origem.items():
                empresa_id, empresa = obter_id_empresa(origem_empresa)
                mapa_motoristas = consolidar_motoristas(empresa_id, empresa, gravar)
                consolidar_veiculos(empresa_id, gravar)
                mapa_veiculos = {placa_chave(v["placa"]): v["id"] for v in db.listar_veiculos(empresa_id)}
                motoristas_origem = {x["id"]: x for x in origem.execute("SELECT * FROM motoristas WHERE empresa_id=?", (origem_empresa_id,))}
                veiculos_origem = {x["id"]: x for x in origem.execute("SELECT * FROM veiculos WHERE empresa_id=?", (origem_empresa_id,))}
                existentes = {assinatura_viagem(empresa_id, v["motorista_id"], v["veiculo_id"], v): v["id"] for v in db.listar_viagens(empresa_id)}
                for viagem in origem.execute("SELECT * FROM viagens WHERE empresa_id=? ORDER BY id", (origem_empresa_id,)):
                    motorista = motorista_destino(mapa_motoristas, empresa_id, empresa, motoristas_origem[viagem["motorista_id"]], gravar)
                    veiculo = veiculo_destino(mapa_veiculos, empresa_id, veiculos_origem[viagem["veiculo_id"]], motorista, gravar)
                    chave = assinatura_viagem(empresa_id, motorista, veiculo, viagem)
                    destino_viagem = existentes.get(chave)
                    if destino_viagem:
                        resumo["viagens_existentes"] += 1
                    elif gravar:
                        destino_viagem = db.criar_viagem(
                            empresa_id=empresa_id, motorista_id=motorista, veiculo_id=veiculo,
                            data_inicio=viagem["data_inicio"], data_fim=valor(viagem, "data_fim"), origem=valor(viagem, "origem"),
                            destino=valor(viagem, "destino"), motivo=valor(viagem, "motivo"), cliente_atividade=valor(viagem, "cliente_atividade"),
                            hodometro_inicio=valor(viagem, "hodometro_inicio", 0) or 0, hodometro_fim=valor(viagem, "hodometro_fim"),
                            media_computador_bordo=valor(viagem, "media_computador_bordo"), valor_adiantamento=valor(viagem, "valor_adiantamento", 0) or 0, valor_devolvido=valor(viagem, "valor_devolvido", 0) or 0,
                            valor_nf_ida=valor(viagem, "valor_nf_ida", 0) or 0, valor_nf_retorno=valor(viagem, "valor_nf_retorno", 0) or 0,
                            status=valor(viagem, "status", "Finalizada") or "Finalizada", observacoes=valor(viagem, "observacoes"),
                        )
                        existentes[chave] = destino_viagem
                        resumo["viagens_importadas"] += 1
                    else:
                        resumo["viagens_importadas"] += 1
                        continue
                    for despesa in origem.execute("SELECT * FROM despesas WHERE viagem_id=?", (viagem["id"],)):
                        ja_existe = db._one("SELECT 1 FROM despesas WHERE viagem_id=? AND categoria=? AND data=? AND valor=? AND COALESCE(descricao,'')=COALESCE(?, '')", (destino_viagem, despesa["categoria"], despesa["data"], despesa["valor"], valor(despesa, "descricao", "")))
                        if not ja_existe and gravar:
                            db.criar_despesa(viagem_id=destino_viagem, categoria=despesa["categoria"], data=despesa["data"], valor=despesa["valor"], litros=valor(despesa, "litros"), local_abastecimento=valor(despesa, "local_abastecimento"), forma_pagamento=valor(despesa, "forma_pagamento"), descricao=valor(despesa, "descricao"), estabelecimento=valor(despesa, "estabelecimento"), quilometragem=valor(despesa, "quilometragem"), status=valor(despesa, "status", "Pendente") or "Pendente")
                            resumo["despesas"] += 1
                    for carga in origem.execute("SELECT * FROM cargas WHERE viagem_id=?", (viagem["id"],)):
                        ja_existe = db._one("SELECT 1 FROM cargas WHERE viagem_id=? AND empresa_cliente=? AND tipo=? AND data=? AND valor=?", (destino_viagem, carga["empresa_cliente"], carga["tipo"], carga["data"], carga["valor"]))
                        if not ja_existe and gravar:
                            db.criar_carga(viagem_id=destino_viagem, empresa_cliente=carga["empresa_cliente"], tipo=carga["tipo"], data=carga["data"], valor=carga["valor"], descricao=valor(carga, "descricao"))
                            resumo["cargas"] += 1
                resumo[f"codigos_{empresa}"] = definir_codigos(empresa_id, empresa, gravar)
                resumo[f"codigos_veiculos_{empresa}"] = definir_codigos_veiculos(empresa_id, empresa, gravar)
            return resumo
        finally:
            origem.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("arquivo_zip")
    parser.add_argument("--dry-run", action="store_true")
    argumentos = parser.parse_args()
    if not os.path.exists(argumentos.arquivo_zip):
        raise SystemExit("Arquivo ZIP não encontrado.")
    if not db.USANDO_POSTGRES:
        raise SystemExit("Defina DATABASE_URL do Neon antes de importar. Nada foi alterado.")
    resultado = importar(argumentos.arquivo_zip, gravar=not argumentos.dry_run)
    print(("Simulação concluída:" if argumentos.dry_run else "Importação concluída:"), resultado)

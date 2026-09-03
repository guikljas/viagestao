"""Consolida e padroniza motoristas já presentes no banco Neon.

Uso seguro (primeiro apenas confere):
  python normalizar_motoristas.py --empresa MARK --dry-run
Depois de revisar o resumo:
  python normalizar_motoristas.py --empresa MARK --confirmar
"""

import argparse

import database as db
from importar_historico_zip import consolidar_motoristas, definir_codigos, nome_padrao


def obter_empresa(nome):
    empresa = next(
        (item for item in db.listar_empresas() if item["nome"] == nome), None
    )
    if not empresa:
        raise SystemExit(f"Empresa {nome} não encontrada no banco.")
    return empresa


def grupos_duplicados(empresa_id, empresa):
    grupos = {}
    for motorista in db.listar_motoristas(empresa_id):
        grupos.setdefault(nome_padrao(empresa, motorista["nome"]), []).append(motorista)
    return {nome: itens for nome, itens in grupos.items() if len(itens) > 1}


def executar(nome_empresa, gravar):
    if not db.USANDO_POSTGRES:
        raise SystemExit(
            "Defina DATABASE_URL do Neon antes de executar. Nenhum dado foi alterado."
        )
    db.inicializar()
    empresa = obter_empresa(nome_empresa)
    duplicados = grupos_duplicados(empresa["id"], nome_empresa)
    quantidade_antes = len(db.listar_motoristas(empresa["id"]))
    print(f"Empresa: {nome_empresa}")
    print(f"Motoristas antes: {quantidade_antes}")
    if duplicados:
        print("Grupos que serão consolidados:")
        for padrao, itens in duplicados.items():
            nomes = ", ".join(f"#{item['id']} {item['nome']}" for item in itens)
            print(f"- {padrao}: {nomes}")
    else:
        print(
            "Não há duplicidades conhecidas; somente caixa alta e códigos serão ajustados."
        )
    quantidade_prevista = quantidade_antes - sum(
        len(itens) - 1 for itens in duplicados.values()
    )
    consolidar_motoristas(empresa["id"], nome_empresa, gravar=gravar)
    if gravar:
        quantidade_depois = definir_codigos(empresa["id"], nome_empresa, gravar=True)
        prefixo = "MK" if nome_empresa == "MARK" else "ERX"
        print(
            f"Concluído: {quantidade_depois} motoristas mantidos e códigos {prefixo}-### atualizados."
        )
    else:
        print(
            f"Simulação concluída: {quantidade_prevista} motoristas permanecerão. Execute novamente com --confirmar para gravar."
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--empresa", choices=("MARK", "ERIMAX"), default="MARK")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirmar", action="store_true")
    args = parser.parse_args()
    if args.dry_run and args.confirmar:
        raise SystemExit("Use apenas --dry-run ou --confirmar.")
    executar(args.empresa, gravar=args.confirmar)

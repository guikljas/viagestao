"""Dados compartilhados entre a tela e a apresentação do relatório mensal."""

from datetime import date

import database as db
from analise import analisar_consumo_mes, analisar_mes


MESES = (
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
)


def nome_mes(mes):
    return MESES[mes - 1]


def obter_dados_relatorio_mensal(empresa_id, ano, mes):
    """Centraliza a mesma leitura usada pelo relatório mensal web.

    O filtro de viagens segue a regra já publicada na tela: viagens iniciadas
    no mês, enquanto despesas e cargas respeitam suas próprias datas de
    lançamento. Essa separação impede divergências entre a tela e o PPTX.
    """
    inicio_mes = date(ano, mes, 1)
    fim_mes = date(ano + 1, 1, 1) if mes == 12 else date(ano, mes + 1, 1)
    viagens = [
        viagem
        for viagem in db.listar_viagens(empresa_id)
        if inicio_mes.isoformat() <= str(viagem["data_inicio"]) < fim_mes.isoformat()
    ]
    despesas = db.listar_despesas_periodo(
        empresa_id, inicio_mes.isoformat(), fim_mes.isoformat()
    )
    cargas = db.listar_cargas_periodo(
        empresa_id, inicio_mes.isoformat(), fim_mes.isoformat()
    )
    dados = analisar_mes(despesas, cargas)

    por_categoria = {}
    for despesa in despesas:
        categoria = despesa["categoria"] or "SEM CATEGORIA"
        por_categoria[categoria] = por_categoria.get(categoria, 0.0) + float(
            despesa["valor"] or 0
        )
    categorias = [
        {"nome": nome, "valor": valor}
        for nome, valor in sorted(
            por_categoria.items(), key=lambda item: item[1], reverse=True
        )
    ]
    total_categoria = sum(item["valor"] for item in categorias)
    for item in categorias:
        item["percentual"] = (
            item["valor"] / total_categoria * 100 if total_categoria else 0.0
        )

    indice_atual = ano * 12 + (mes - 1)
    indice_inicial = indice_atual - 5
    inicio_historico = date(indice_inicial // 12, indice_inicial % 12 + 1, 1)
    despesas_historico = db.listar_despesas_periodo(
        empresa_id, inicio_historico.isoformat(), fim_mes.isoformat()
    )
    cargas_historico = db.listar_cargas_periodo(
        empresa_id, inicio_historico.isoformat(), fim_mes.isoformat()
    )
    historico = []
    for deslocamento in range(5, -1, -1):
        indice = indice_atual - deslocamento
        ano_item = indice // 12
        mes_item = indice % 12 + 1
        prefixo = f"{ano_item:04d}-{mes_item:02d}"
        historico.append(
            {
                "rotulo": f"{mes_item:02d}/{ano_item}",
                "despesa": sum(
                    float(item["valor"] or 0)
                    for item in despesas_historico
                    if str(item["data"]).startswith(prefixo)
                ),
                "receita": sum(
                    float(item["valor"] or 0)
                    for item in cargas_historico
                    if str(item["data"]).startswith(prefixo)
                ),
            }
        )

    despesas_por_viagem = {viagem["id"]: [] for viagem in viagens}
    cargas_por_viagem = {viagem["id"]: [] for viagem in viagens}
    for despesa in despesas:
        if despesa["viagem_id"] in despesas_por_viagem:
            despesas_por_viagem[despesa["viagem_id"]].append(despesa)
    for carga in cargas:
        if carga["viagem_id"] in cargas_por_viagem:
            cargas_por_viagem[carga["viagem_id"]].append(carga)

    consumo = analisar_consumo_mes(
        [(viagem, despesas_por_viagem[viagem["id"]]) for viagem in viagens],
        veiculos=db.listar_veiculos(empresa_id),
        motoristas=db.listar_motoristas(empresa_id),
    )

    viagens_resumo = []
    motoristas = {}
    rotas = {}
    km_total = 0.0
    for viagem in viagens:
        viagem_despesas = despesas_por_viagem[viagem["id"]]
        viagem_cargas = cargas_por_viagem[viagem["id"]]
        despesa_total = sum(float(item["valor"] or 0) for item in viagem_despesas)
        receita_total = sum(float(item["valor"] or 0) for item in viagem_cargas)
        km = 0.0
        if viagem["hodometro_fim"] is not None:
            km = max(
                0.0,
                float(viagem["hodometro_fim"]) - float(viagem["hodometro_inicio"] or 0),
            )
        km_total += km
        rota = f"{viagem['origem'] or '—'} → {viagem['destino'] or '—'}"
        resumo = {
            "id": viagem["id"],
            "motorista": viagem["motorista_nome"],
            "veiculo": viagem["veiculo_placa"],
            "rota": rota,
            "km": km,
            "despesa": despesa_total,
            "receita": receita_total,
        }
        viagens_resumo.append(resumo)

        motorista = motoristas.setdefault(
            viagem["motorista_nome"],
            {"motorista": viagem["motorista_nome"], "viagens": 0, "km": 0.0, "despesa": 0.0, "receita": 0.0},
        )
        motorista["viagens"] += 1
        motorista["km"] += km
        motorista["despesa"] += despesa_total
        motorista["receita"] += receita_total

        rota_item = rotas.setdefault(
            rota,
            {"rota": rota, "viagens": 0, "km": 0.0, "despesa": 0.0, "receita": 0.0},
        )
        rota_item["viagens"] += 1
        rota_item["km"] += km
        rota_item["despesa"] += despesa_total
        rota_item["receita"] += receita_total

    return {
        "ano": ano,
        "mes": mes,
        "nome_mes": nome_mes(mes),
        "inicio": inicio_mes,
        "fim": fim_mes,
        "viagens": viagens,
        "despesas": despesas,
        "cargas": cargas,
        "dados": dados,
        "categorias": categorias,
        "historico": historico,
        "consumo": consumo,
        "viagens_resumo": sorted(viagens_resumo, key=lambda item: item["receita"], reverse=True),
        "motoristas": sorted(motoristas.values(), key=lambda item: item["receita"], reverse=True),
        "rotas": sorted(rotas.values(), key=lambda item: item["receita"], reverse=True),
        "km_total": km_total,
        "resultado": float(dados["total_receita_mes"]) - float(dados["total_despesa_mes"]),
    }

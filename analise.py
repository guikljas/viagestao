"""
Calculos de consumo de combustivel por viagem: km rodado, litros abastecidos
(via despesas categoria=COMBUSTIVEL), consumo real (km/L) confrontado com a
media do computador de bordo informada na viagem, e custo medio do litro.
"""

import unicodedata

from utils import fmt_numero

LIMIAR_ALERTA_PCT = 10.0  # divergencia >= 10% entre consumo real e painel vira alerta
LIMIAR_ALERTA_PRECO_PCT = 5.0  # preco pago na viagem >= 5% acima do preco de Assis vira alerta


def categoria_chave(valor):
    texto = unicodedata.normalize("NFKD", valor or "").encode("ascii", "ignore").decode("ascii")
    return texto.strip().upper().replace(" ", "_")


def analisar_viagem(viagem: dict, despesas: list, cargas: list = None) -> dict:
    cargas = cargas or []
    despesas_combustivel = [d for d in despesas if categoria_chave(d["categoria"]) == "COMBUSTIVEL"]
    total_litros = sum((d["litros"] or 0) for d in despesas_combustivel)
    total_valor_combustivel = sum(d["valor"] for d in despesas_combustivel)

    km_rodado = None
    if viagem["hodometro_fim"] is not None:
        km_rodado = viagem["hodometro_fim"] - viagem["hodometro_inicio"]

    consumo_real = None
    if km_rodado and total_litros:
        consumo_real = km_rodado / total_litros

    custo_medio_litro = None
    if total_litros:
        custo_medio_litro = total_valor_combustivel / total_litros

    media_painel = viagem["media_computador_bordo"]
    diferenca_abs = None
    diferenca_pct = None
    feedback = "SEM DADOS SUFICIENTES"
    if consumo_real is not None and media_painel:
        diferenca_abs = consumo_real - media_painel
        diferenca_pct = (diferenca_abs / media_painel) * 100
        if abs(diferenca_pct) < LIMIAR_ALERTA_PCT:
            feedback = "CONSUMO CONFERE COM O PAINEL"
        elif diferenca_pct > 0:
            feedback = "LITROS DAS NOTAS ABAIXO DO ESPERADO (rodou mais km por litro que o painel indica -- abasteceu menos do que o painel sugeriria, conferir se faltam notas)"
        else:
            feedback = "LITROS DAS NOTAS ACIMA DO ESPERADO (rodou menos km por litro do que o painel indica -- consumo maior que o esperado, possivel desvio, vazamento ou motor fora de ponto)"

    despesas_assis = [d for d in despesas_combustivel if d["local_abastecimento"] == "ASSIS"]
    despesas_estrada = [d for d in despesas_combustivel if d["local_abastecimento"] == "VIAGEM"]
    litros_assis = sum((d["litros"] or 0) for d in despesas_assis)
    valor_assis = sum(d["valor"] for d in despesas_assis)
    litros_estrada = sum((d["litros"] or 0) for d in despesas_estrada)
    valor_estrada = sum(d["valor"] for d in despesas_estrada)

    preco_medio_assis = (valor_assis / litros_assis) if litros_assis else None
    preco_medio_estrada = (valor_estrada / litros_estrada) if litros_estrada else None

    diferenca_preco_pct = None
    feedback_preco = "SEM DADOS SUFICIENTES PRA COMPARAR (falta abastecimento marcado como Assis ou como viagem)"
    alerta_preco = False
    if preco_medio_assis and preco_medio_estrada:
        diferenca_preco_pct = ((preco_medio_estrada - preco_medio_assis) / preco_medio_assis) * 100
        if diferenca_preco_pct <= LIMIAR_ALERTA_PRECO_PCT:
            feedback_preco = "PRECO PAGO NA VIAGEM DENTRO DO PRATICADO EM ASSIS"
        else:
            feedback_preco = f"PRECO PAGO NA VIAGEM {fmt_numero(diferenca_preco_pct, 1)}% ACIMA DO PRATICADO EM ASSIS -- conferir se abasteceu em posto mais caro que o necessario"
            alerta_preco = True

    totais_por_categoria = {}
    for d in despesas:
        totais_por_categoria[d["categoria"]] = totais_por_categoria.get(d["categoria"], 0) + d["valor"]
    total_geral = sum(totais_por_categoria.values())

    qtd_sinistros = sum(1 for d in despesas if categoria_chave(d["categoria"]) == "SINISTRO")

    adiantamento = viagem["valor_adiantamento"] or 0
    devolvido = viagem["valor_devolvido"] or 0
    saldo = adiantamento - devolvido - total_geral  # esperado: 0 (adiantamento = gasto + devolvido)
    if adiantamento == 0 and devolvido == 0:
        feedback_adiantamento = "SEM ADIANTAMENTO REGISTRADO"
    elif abs(saldo) < 0.01:
        feedback_adiantamento = "ADIANTAMENTO CONFERE (gasto + devolvido = adiantamento)"
    elif saldo > 0:
        feedback_adiantamento = f"FALTA PRESTAR CONTAS: R$ {fmt_numero(saldo)} do adiantamento nao aparece em despesas nem foi devolvido"
    else:
        feedback_adiantamento = f"MOTORISTA GASTOU/DEVOLVEU R$ {fmt_numero(abs(saldo))} A MAIS DO QUE RECEBEU DE ADIANTAMENTO"

    # legado: algumas viagens antigas usaram os campos soltos de NF ida/retorno
    # antes de existir o detalhamento por empresa-cliente (cargas). Mantido
    # somado na receita pra nao perder valor ja lancado, mas o lancamento novo
    # deve usar "Lancar Carga" (por empresa, entrega/coleta).
    valor_nf_ida = viagem["valor_nf_ida"] or 0
    valor_nf_retorno = viagem["valor_nf_retorno"] or 0

    cargas_por_empresa = {}
    for c in cargas:
        emp = c["empresa_cliente"]
        d = cargas_por_empresa.setdefault(emp, {"entrega": 0.0, "coleta": 0.0})
        if c["tipo"] == "ENTREGA":
            d["entrega"] += c["valor"]
        else:
            d["coleta"] += c["valor"]
    total_entrega = sum(d["entrega"] for d in cargas_por_empresa.values())
    total_coleta = sum(d["coleta"] for d in cargas_por_empresa.values())
    total_cargas = total_entrega + total_coleta

    # rateio do custo da viagem entre as empresas atendidas, proporcional a
    # quanto cada uma representa da receita da viagem (faturamento + retorno).
    # O valor legado de NF ida/retorno (sem empresa vinculada) nao entra no
    # rateio -- so as cargas lancadas por "Lancar Carga" tem empresa conhecida.
    for emp, d in cargas_por_empresa.items():
        d["total"] = d["entrega"] + d["coleta"]
        d["percentual_receita"] = (d["total"] / total_cargas * 100) if total_cargas else None
        d["custo_alocado"] = (total_geral * d["total"] / total_cargas) if total_cargas else None

    receita_total = total_cargas + valor_nf_ida + valor_nf_retorno

    percentual_custo_receita = (total_geral / receita_total * 100) if receita_total else None

    return {
        "adiantamento": adiantamento,
        "devolvido": devolvido,
        "saldo_adiantamento": saldo,
        "feedback_adiantamento": feedback_adiantamento,
        "km_rodado": km_rodado,
        "total_litros": total_litros,
        "total_valor_combustivel": total_valor_combustivel,
        "consumo_real": consumo_real,
        "media_painel": media_painel,
        "diferenca_abs": diferenca_abs,
        "diferenca_pct": diferenca_pct,
        "custo_medio_litro": custo_medio_litro,
        "feedback": feedback,
        "totais_por_categoria": totais_por_categoria,
        "total_geral": total_geral,
        "qtd_sinistros": qtd_sinistros,
        "alerta": diferenca_pct is not None and abs(diferenca_pct) >= LIMIAR_ALERTA_PCT,
        "preco_medio_assis": preco_medio_assis,
        "preco_medio_estrada": preco_medio_estrada,
        "diferenca_preco_pct": diferenca_preco_pct,
        "feedback_preco": feedback_preco,
        "alerta_preco": alerta_preco,
        "valor_nf_ida": valor_nf_ida,
        "valor_nf_retorno": valor_nf_retorno,
        "cargas_por_empresa": cargas_por_empresa,
        "total_entrega": total_entrega,
        "total_coleta": total_coleta,
        "receita_total": receita_total,
        "percentual_custo_receita": percentual_custo_receita,
    }


def analisar_mes(despesas_mes: list, cargas_mes: list) -> dict:
    """Fechamento mensal: total de entrega e coleta por empresa-cliente
    atendida, e quanto cada uma representa sobre o total de despesa de
    frete do mes (soma de TODAS as despesas de TODAS as viagens do mes,
    qualquer categoria -- e o custo total de rodar a frota naquele mes)."""
    total_despesa_mes = sum(d["valor"] for d in despesas_mes)

    por_empresa = {}
    for c in cargas_mes:
        emp = c["empresa_cliente"]
        d = por_empresa.setdefault(emp, {"entrega": 0.0, "coleta": 0.0})
        if c["tipo"] == "ENTREGA":
            d["entrega"] += c["valor"]
        else:
            d["coleta"] += c["valor"]

    total_receita_mes = sum(d["entrega"] + d["coleta"] for d in por_empresa.values())

    # rateio: despesa (custo) dividida pela receita, alocada por empresa
    # proporcional a quanto cada uma representa do faturamento do mes.
    # Sempre entrega os dois numeros juntos -- valor (R$) alocado a cada
    # empresa e o percentual que a despesa representa sobre a receita dela.
    for emp, d in por_empresa.items():
        d["total"] = d["entrega"] + d["coleta"]
        d["percentual_receita"] = (d["total"] / total_receita_mes * 100) if total_receita_mes else None
        d["despesa_alocada"] = (total_despesa_mes * d["total"] / total_receita_mes) if total_receita_mes else None
        d["percentual_despesa_sobre_receita"] = (
            d["despesa_alocada"] / d["total"] * 100
        ) if d["total"] else None

    percentual_despesa_sobre_receita_total = (total_despesa_mes / total_receita_mes * 100) if total_receita_mes else None

    return {
        "total_despesa_mes": total_despesa_mes,
        "total_receita_mes": total_receita_mes,
        "percentual_despesa_sobre_receita": percentual_despesa_sobre_receita_total,
        "por_empresa": por_empresa,
    }


def analisar_consumo_mes(viagens_com_despesas: list, veiculos: list = None, motoristas: list = None) -> dict:
    """viagens_com_despesas: lista de tuplas (viagem, despesas_da_viagem) do mes.
    Soma km rodado e litros abastecidos (despesas categoria=COMBUSTIVEL) agrupando
    por veiculo (placa) e por motorista, e calcula a media de consumo (km/L) de
    cada um no mes -- viagens sem hodometro final ou sem litros lancados nao
    entram na conta (nao da pra saber km/litros delas)."""
    # A visão mensal também é um painel de frota: veículos e motoristas sem
    # consumo no período precisam aparecer, em vez de desaparecer da análise.
    por_veiculo = {
        item["placa"]: {"km": 0.0, "litros": 0.0, "viagens": 0, "consumo_medio": None}
        for item in (veiculos or [])
    }
    por_motorista = {
        item["nome"]: {"km": 0.0, "litros": 0.0, "viagens": 0, "consumo_medio": None}
        for item in (motoristas or [])
    }

    for viagem, despesas in viagens_com_despesas:
        if viagem["hodometro_fim"] is None:
            continue
        km = viagem["hodometro_fim"] - viagem["hodometro_inicio"]
        litros = sum((d["litros"] or 0) for d in despesas if categoria_chave(d["categoria"]) == "COMBUSTIVEL")
        if km <= 0 or litros <= 0:
            continue

        placa = viagem["veiculo_placa"]
        dv = por_veiculo.setdefault(placa, {"km": 0.0, "litros": 0.0, "viagens": 0})
        dv["km"] += km
        dv["litros"] += litros
        dv["viagens"] += 1

        nome = viagem["motorista_nome"]
        dm = por_motorista.setdefault(nome, {"km": 0.0, "litros": 0.0, "viagens": 0})
        dm["km"] += km
        dm["litros"] += litros
        dm["viagens"] += 1

    for d in por_veiculo.values():
        d["consumo_medio"] = (d["km"] / d["litros"]) if d["litros"] else None
    for d in por_motorista.values():
        d["consumo_medio"] = (d["km"] / d["litros"]) if d["litros"] else None

    return {"por_veiculo": por_veiculo, "por_motorista": por_motorista}

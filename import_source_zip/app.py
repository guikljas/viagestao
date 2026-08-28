import streamlit as st
from datetime import date

import database as db
from analise import analisar_viagem, analisar_mes, analisar_consumo_mes
from relatorio import gerar_relatorio
from utils import parse_numero, fmt_numero, fmt_data, fmt_codigo

st.set_page_config(page_title="Despesas de Viagem - Motoristas", layout="wide")
db.inicializar()

st.title("Controle de Despesas de Viagem")

empresas = db.listar_empresas()
mapa_empresas = {e["nome"]: e["id"] for e in empresas}

pagina = st.sidebar.radio(
    "Menu",
    ["Nova Viagem", "Fechar / Atualizar Viagem", "Lancar Despesa", "Lancar Carga",
     "Consultar Viagens", "Relatorio Mensal", "Relatorio Excel"],
)

# ---------------------------------------------------------------- Nova Viagem
if pagina == "Nova Viagem":
    st.header("Registrar Nova Viagem")
    with st.form("form_nova_viagem"):
        col1, col2 = st.columns(2)
        with col1:
            empresa_nome = st.selectbox("Empresa", list(mapa_empresas.keys()))
            motorista_nome = st.text_input("Motorista (nome)")
            motorista_codigo = st.text_input("Codigo do motorista (opcional)", "", help="Ex: 01, 07")
            veiculo_placa = st.text_input("Placa do veiculo")
            veiculo_codigo = st.text_input("Codigo do veiculo (opcional)", "", help="Ex: 01, 02")
            veiculo_desc = st.text_input("Descricao do veiculo (opcional)", "")
        with col2:
            data_inicio = st.date_input("Data de inicio", value=date.today(), format="DD/MM/YYYY")
            origem = st.text_input("Origem")
            destino = st.text_input("Destino")
            hodometro_inicio_txt = st.text_input("Hodometro de inicio (km)", value="", help="Ex: 120000 ou 120000,50")
            valor_adiantamento_txt = st.text_input("Valor do adiantamento (R$)", value="", help="Ex: 1000 ou 1000,00")
        enviado = st.form_submit_button("Registrar viagem")

    if enviado:
        if not motorista_nome or not veiculo_placa:
            st.error("Preencha motorista e placa do veiculo.")
        elif not hodometro_inicio_txt.strip():
            st.error("Preencha o hodometro de inicio.")
        else:
            try:
                hodometro_inicio = parse_numero(hodometro_inicio_txt)
                valor_adiantamento = parse_numero(valor_adiantamento_txt)
            except ValueError as e:
                st.error(str(e))
                st.stop()
            empresa_id = mapa_empresas[empresa_nome]
            motorista_id = db.obter_ou_criar_motorista(motorista_nome.strip(), empresa_id, motorista_codigo.strip())
            veiculo_id = db.obter_ou_criar_veiculo(veiculo_placa, empresa_id, veiculo_desc, veiculo_codigo.strip())
            viagem_id = db.criar_viagem(
                empresa_id=empresa_id, motorista_id=motorista_id, veiculo_id=veiculo_id,
                data_inicio=str(data_inicio), data_fim=None, origem=origem, destino=destino,
                hodometro_inicio=hodometro_inicio, hodometro_fim=None,
                media_computador_bordo=None, valor_adiantamento=valor_adiantamento, observacoes=None,
            )
            st.success(f"Viagem #{viagem_id} registrada para {motorista_nome} ({empresa_nome}).")

# ------------------------------------------------------ Fechar / Atualizar Viagem
elif pagina == "Fechar / Atualizar Viagem":
    st.header("Fechar ou Atualizar Viagem")
    empresa_nome = st.selectbox("Empresa", list(mapa_empresas.keys()), key="fech_empresa")
    empresa_id = mapa_empresas[empresa_nome]
    viagens_abertas = db.listar_viagens(empresa_id=empresa_id)
    if not viagens_abertas:
        st.info("Nenhuma viagem cadastrada para essa empresa ainda.")
    else:
        opcoes = {
            f"#{v['id']} - {fmt_codigo(v['motorista_nome'], v['motorista_codigo'])} ({fmt_codigo(v['veiculo_placa'], v['veiculo_codigo'])}) - inicio {fmt_data(v['data_inicio'])}"
            + (" [ABERTA]" if v["hodometro_fim"] is None else " [fechada]"): v["id"]
            for v in viagens_abertas
        }
        escolha = st.selectbox("Viagem", list(opcoes.keys()))
        viagem = db.obter_viagem(opcoes[escolha])

        st.caption(f"Hodometro de inicio registrado nessa viagem: {fmt_numero(viagem['hodometro_inicio'], 0)} km")
        with st.form("form_fechar_viagem"):
            data_fim = st.date_input("Data de fim", value=date.today(), format="DD/MM/YYYY")
            hodometro_fim_txt = st.text_input(
                "Hodometro final (km) -- valor real do final da viagem, diferente do hodometro de inicio",
                value=str(viagem["hodometro_fim"]) if viagem["hodometro_fim"] is not None else "",
                help="Ex: 120800 ou 120800,50",
            )
            media_painel_txt = st.text_input(
                "Media do computador de bordo (km/L)",
                value=str(viagem["media_computador_bordo"]) if viagem["media_computador_bordo"] is not None else "",
                help="Ex: 3,2 ou 3.2",
            )
            valor_devolvido_txt = st.text_input(
                "Valor devolvido pelo motorista (R$)",
                value=str(viagem["valor_devolvido"]) if viagem["valor_devolvido"] else "",
                help="Ex: 200 ou 200,00",
            )
            observacoes = st.text_area("Observacoes", value=viagem["observacoes"] or "")
            enviado = st.form_submit_button("Salvar")

        if viagem["valor_adiantamento"]:
            st.caption(f"Adiantamento recebido nessa viagem: R$ {fmt_numero(viagem['valor_adiantamento'])}")
        if viagem["valor_nf_ida"] or viagem["valor_nf_retorno"]:
            st.caption(
                f"Valor legado de NF ida/retorno lancado antes de existir 'Lancar Carga': "
                f"R$ {fmt_numero(viagem['valor_nf_ida'])} / R$ {fmt_numero(viagem['valor_nf_retorno'])} "
                f"(continua somado na receita da viagem)."
            )
        st.caption("Pra lancar receita de entrega/coleta por empresa atendida, use a tela 'Lancar Carga'.")

        if enviado:
            if not hodometro_fim_txt.strip():
                st.error("Preencha o hodometro final.")
                st.stop()
            try:
                hodometro_fim = parse_numero(hodometro_fim_txt)
                media_painel = parse_numero(media_painel_txt)
                valor_devolvido = parse_numero(valor_devolvido_txt)
            except ValueError as e:
                st.error(str(e))
                st.stop()
            if hodometro_fim == viagem["hodometro_inicio"]:
                st.error("Hodometro final igual ao inicial -- confira o valor real do hodometro no fim da viagem.")
                st.stop()
            db.atualizar_viagem(
                viagem["id"], data_fim=str(data_fim), hodometro_fim=hodometro_fim,
                media_computador_bordo=media_painel, valor_devolvido=valor_devolvido,
                valor_nf_ida=viagem["valor_nf_ida"], valor_nf_retorno=viagem["valor_nf_retorno"],
                observacoes=observacoes,
            )
            st.success(f"Viagem #{viagem['id']} atualizada.")

        st.divider()
        st.caption("Excluir viagem (remove tambem todas as despesas lancadas nela)")
        chave_confirma = f"confirma_exclusao_viagem_{viagem['id']}"
        if not st.session_state.get(chave_confirma):
            if st.button("Excluir esta viagem", key=f"btn_excluir_{viagem['id']}"):
                st.session_state[chave_confirma] = True
                st.rerun()
        else:
            st.warning(f"Confirma excluir a viagem #{viagem['id']} de {viagem['motorista_nome']} e todas as suas despesas? Essa acao nao pode ser desfeita.")
            colc1, colc2 = st.columns(2)
            if colc1.button("Sim, excluir definitivamente", key=f"btn_confirma_{viagem['id']}"):
                db.excluir_viagem(viagem["id"])
                st.session_state.pop(chave_confirma, None)
                st.success(f"Viagem #{viagem['id']} excluida.")
                st.rerun()
            if colc2.button("Cancelar", key=f"btn_cancela_{viagem['id']}"):
                st.session_state.pop(chave_confirma, None)
                st.rerun()

# --------------------------------------------------------------- Lancar Despesa
elif pagina == "Lancar Despesa":
    st.header("Lancar Despesa de Viagem")
    empresa_nome = st.selectbox("Empresa", list(mapa_empresas.keys()), key="desp_empresa")
    empresa_id = mapa_empresas[empresa_nome]
    viagens = db.listar_viagens(empresa_id=empresa_id)
    if not viagens:
        st.info("Nenhuma viagem cadastrada para essa empresa ainda. Registre uma viagem primeiro.")
    else:
        opcoes = {
            f"#{v['id']} - {fmt_codigo(v['motorista_nome'], v['motorista_codigo'])} ({fmt_codigo(v['veiculo_placa'], v['veiculo_codigo'])}) - inicio {fmt_data(v['data_inicio'])}": v["id"]
            for v in viagens
        }
        escolha = st.selectbox("Viagem", list(opcoes.keys()))
        viagem_id = opcoes[escolha]

        with st.form("form_despesa", clear_on_submit=True):
            categoria = st.selectbox("Categoria", db.CATEGORIAS)
            data_despesa = st.date_input("Data", value=date.today(), format="DD/MM/YYYY")
            valor_txt = st.text_input("Valor (R$)", value="", help="Ex: 150 ou 150,00")
            litros_txt = st.text_input(
                "Litros abastecidos (preencher so se a categoria for COMBUSTIVEL)",
                value="", help="Ex: 200 ou 200,50",
            )
            local_abastecimento = st.radio(
                "Onde abasteceu (so pra COMBUSTIVEL)",
                db.LOCAIS_ABASTECIMENTO,
                format_func=lambda x: "Assis (base)" if x == "ASSIS" else "Na viagem (estrada)",
                horizontal=True,
            )
            forma_pagamento = st.radio(
                "Forma de pagamento",
                db.FORMAS_PAGAMENTO,
                format_func=lambda x: "Dinheiro" if x == "DINHEIRO" else "Cartao",
                horizontal=True,
            )
            descricao = st.text_input("Descricao / observacao (opcional)")
            enviado = st.form_submit_button("Lancar despesa")

        if enviado:
            if not valor_txt.strip():
                st.error("Preencha o valor da despesa.")
                st.stop()
            if categoria == "COMBUSTIVEL" and not (litros_txt or "").strip():
                st.error("Preencha os litros abastecidos (categoria COMBUSTIVEL).")
                st.stop()
            try:
                valor = parse_numero(valor_txt)
                litros = parse_numero(litros_txt) if categoria == "COMBUSTIVEL" else None
            except ValueError as e:
                st.error(str(e))
                st.stop()
            db.criar_despesa(
                viagem_id=viagem_id, categoria=categoria, data=str(data_despesa),
                valor=valor, litros=litros,
                local_abastecimento=local_abastecimento if categoria == "COMBUSTIVEL" else None,
                forma_pagamento=forma_pagamento,
                descricao=descricao,
            )
            st.success(f"Despesa de {categoria} lancada na viagem #{viagem_id}.")

        st.subheader("Despesas ja lancadas nessa viagem")
        despesas = db.listar_despesas(viagem_id=viagem_id)
        if despesas:
            for d in despesas:
                c1, c2, c3, c4, c5, c6, c7, c8 = st.columns([2, 2, 2, 2, 2, 2, 2, 1])
                c1.write(d["categoria"])
                c2.write(fmt_data(d["data"]))
                c3.write(f"R$ {fmt_numero(d['valor'])}")
                c4.write(f"{fmt_numero(d['litros'])} L" if d["litros"] is not None else "-")
                c5.write("Assis" if d["local_abastecimento"] == "ASSIS" else ("Viagem" if d["local_abastecimento"] == "VIAGEM" else "-"))
                c6.write("Dinheiro" if d["forma_pagamento"] == "DINHEIRO" else ("Cartao" if d["forma_pagamento"] == "CARTAO" else "-"))
                c7.write(d["descricao"] or "")
                if c8.button("Excluir", key=f"del_despesa_{d['id']}"):
                    db.excluir_despesa(d["id"])
                    st.rerun()
        else:
            st.write("Nenhuma despesa lancada ainda.")

# --------------------------------------------------------------- Lancar Carga
elif pagina == "Lancar Carga":
    st.header("Lancar Carga de Entrega/Coleta")
    st.caption("Uma viagem pode atender varias empresas -- lance uma carga por empresa atendida (entrega ou coleta).")
    empresa_nome = st.selectbox("Empresa", list(mapa_empresas.keys()), key="carga_empresa")
    empresa_id = mapa_empresas[empresa_nome]
    viagens = db.listar_viagens(empresa_id=empresa_id)
    if not viagens:
        st.info("Nenhuma viagem cadastrada para essa empresa ainda. Registre uma viagem primeiro.")
    else:
        opcoes = {
            f"#{v['id']} - {fmt_codigo(v['motorista_nome'], v['motorista_codigo'])} ({fmt_codigo(v['veiculo_placa'], v['veiculo_codigo'])}) - inicio {fmt_data(v['data_inicio'])}": v["id"]
            for v in viagens
        }
        escolha = st.selectbox("Viagem", list(opcoes.keys()), key="carga_viagem")
        viagem_id = opcoes[escolha]

        clientes_sugeridos = db.listar_clientes_frete(empresa_id)

        with st.form("form_carga", clear_on_submit=True):
            if clientes_sugeridos:
                empresa_cliente_sel = st.selectbox(
                    "Empresa atendida (cliente do frete)",
                    clientes_sugeridos + ["Outra (digitar abaixo)"],
                )
            else:
                empresa_cliente_sel = "Outra (digitar abaixo)"
            empresa_cliente_txt = st.text_input(
                "Nome da empresa atendida (preencher se escolheu 'Outra' acima, ou pra cadastrar a primeira)",
                value="",
            )
            tipo = st.radio("Tipo", db.TIPOS_CARGA, format_func=lambda x: "Entrega" if x == "ENTREGA" else "Coleta", horizontal=True)
            data_carga = st.date_input("Data", value=date.today(), format="DD/MM/YYYY", key="carga_data")
            valor_txt = st.text_input("Valor (R$)", value="", help="Ex: 1200 ou 1200,00")
            descricao = st.text_input("Descricao / observacao (opcional)", key="carga_desc")
            enviado = st.form_submit_button("Lancar carga")

        if enviado:
            empresa_cliente = empresa_cliente_txt.strip() or (
                empresa_cliente_sel if empresa_cliente_sel != "Outra (digitar abaixo)" else ""
            )
            if not empresa_cliente:
                st.error("Informe o nome da empresa atendida.")
                st.stop()
            if not valor_txt.strip():
                st.error("Preencha o valor da carga.")
                st.stop()
            try:
                valor = parse_numero(valor_txt)
            except ValueError as e:
                st.error(str(e))
                st.stop()
            db.criar_carga(
                viagem_id=viagem_id, empresa_cliente=empresa_cliente, tipo=tipo,
                data=str(data_carga), valor=valor, descricao=descricao,
            )
            st.success(f"{'Entrega' if tipo == 'ENTREGA' else 'Coleta'} de {empresa_cliente} lancada na viagem #{viagem_id}.")

        st.subheader("Cargas ja lancadas nessa viagem")
        cargas = db.listar_cargas(viagem_id=viagem_id)
        if cargas:
            for c in cargas:
                cc1, cc2, cc3, cc4, cc5, cc6 = st.columns([3, 2, 2, 2, 3, 1])
                cc1.write(c["empresa_cliente"])
                cc2.write("Entrega" if c["tipo"] == "ENTREGA" else "Coleta")
                cc3.write(fmt_data(c["data"]))
                cc4.write(f"R$ {fmt_numero(c['valor'])}")
                cc5.write(c["descricao"] or "")
                if cc6.button("Excluir", key=f"del_carga_{c['id']}"):
                    db.excluir_carga(c["id"])
                    st.rerun()
        else:
            st.write("Nenhuma carga lancada ainda.")

# --------------------------------------------------------------- Consultar Viagens
elif pagina == "Consultar Viagens":
    st.header("Consultar Viagens e Analise de Consumo")
    empresa_nome = st.selectbox("Empresa", list(mapa_empresas.keys()), key="cons_empresa")
    empresa_id = mapa_empresas[empresa_nome]
    viagens = db.listar_viagens(empresa_id=empresa_id)
    if not viagens:
        st.info("Nenhuma viagem cadastrada para essa empresa ainda.")
    else:
        for v in viagens:
            despesas = db.listar_despesas(viagem_id=v["id"])
            cargas = db.listar_cargas(viagem_id=v["id"])
            a = analisar_viagem(v, despesas, cargas)
            status = "ABERTA" if v["hodometro_fim"] is None else "FECHADA"
            with st.expander(
                f"#{v['id']} - {fmt_codigo(v['motorista_nome'], v['motorista_codigo'])} ({fmt_codigo(v['veiculo_placa'], v['veiculo_codigo'])}) "
                f"{fmt_data(v['data_inicio'])} -> {fmt_data(v['data_fim']) or '...'} [{status}]"
            ):
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Km rodado", fmt_numero(a['km_rodado'], 0) if a["km_rodado"] is not None else "-")
                c2.metric("Consumo real (km/L)", fmt_numero(a['consumo_real']) if a["consumo_real"] is not None else "-")
                c3.metric("Media painel (km/L)", fmt_numero(a['media_painel']) if a["media_painel"] is not None else "-")
                c4.metric("Custo medio litro", f"R$ {fmt_numero(a['custo_medio_litro'], 2)}" if a["custo_medio_litro"] is not None else "-")
                if v["hodometro_fim"] is not None and v["hodometro_fim"] == v["hodometro_inicio"]:
                    st.warning("Hodometro final igual ao inicial (km rodado = 0) -- confira se esqueceu de atualizar o hodometro final em 'Fechar / Atualizar Viagem'.")
                if a["alerta"]:
                    st.error(f"ALERTA: {a['feedback']} (diferenca {fmt_numero(a['diferenca_pct'], 1)}%)")
                elif a["consumo_real"] is not None:
                    st.success(a["feedback"])
                st.write(f"**Total geral gasto:** R$ {fmt_numero(a['total_geral'])}")
                st.write(
                    "Por categoria:",
                    {k: f"R$ {fmt_numero(v)}" for k, v in a["totais_por_categoria"].items()},
                )
                c5, c6, c7 = st.columns(3)
                c5.metric("Adiantamento", f"R$ {fmt_numero(a['adiantamento'])}")
                c6.metric("Devolvido", f"R$ {fmt_numero(a['devolvido'])}")
                c7.metric("Saldo (a prestar contas)", f"R$ {fmt_numero(a['saldo_adiantamento'])}")
                if abs(a["saldo_adiantamento"]) >= 0.01:
                    st.warning(a["feedback_adiantamento"])
                elif a["adiantamento"] or a["devolvido"]:
                    st.success(a["feedback_adiantamento"])
                if a["qtd_sinistros"]:
                    st.warning(f"{a['qtd_sinistros']} sinistro(s) registrado(s) nessa viagem.")

                st.divider()
                st.write("**Receita por empresa atendida (entrega/coleta) e rateio do custo do frete**")
                if a["cargas_por_empresa"]:
                    st.caption(
                        "O custo total da viagem e rateado entre as empresas atendidas, "
                        "proporcional a quanto cada uma representa da receita (entrega+coleta) dessa viagem."
                    )
                    for emp, dd in a["cargas_por_empresa"].items():
                        st.write(
                            f"- **{emp}**: entrega R\\$ {fmt_numero(dd['entrega'])} · "
                            f"coleta R\\$ {fmt_numero(dd['coleta'])} · total R\\$ {fmt_numero(dd['total'])} "
                            f"({fmt_numero(dd['percentual_receita'], 1)}% da receita) "
                            f"→ **deve pagar R\\$ {fmt_numero(dd['custo_alocado'])}** do custo do frete"
                        )
                else:
                    st.caption("Nenhuma carga lancada nessa viagem ainda (use 'Lancar Carga').")
                c8, c9, c10 = st.columns(3)
                c8.metric("Valor da receita", f"R$ {fmt_numero(a['receita_total'])}")
                c9.metric("Valor total frete (despesas)", f"R$ {fmt_numero(a['total_geral'])}")
                c10.metric(
                    "Percentagem do frete sobre a receita",
                    f"{fmt_numero(a['percentual_custo_receita'], 3)}%" if a["percentual_custo_receita"] is not None else "-",
                )

                st.write("**Comparacao de preco do combustivel: Assis x estrada**")
                c12, c13, c14 = st.columns(3)
                c12.metric("Preco medio em Assis", f"R$ {fmt_numero(a['preco_medio_assis'])}" if a["preco_medio_assis"] is not None else "-")
                c13.metric("Preco medio na estrada", f"R$ {fmt_numero(a['preco_medio_estrada'])}" if a["preco_medio_estrada"] is not None else "-")
                c14.metric("Diferenca", f"{fmt_numero(a['diferenca_preco_pct'], 1)}%" if a["diferenca_preco_pct"] is not None else "-")
                if a["alerta_preco"]:
                    st.error(f"ALERTA: {a['feedback_preco']}")
                elif a["preco_medio_assis"] is not None and a["preco_medio_estrada"] is not None:
                    st.success(a["feedback_preco"])
                else:
                    st.caption(a["feedback_preco"])

# --------------------------------------------------------------- Relatorio Mensal
elif pagina == "Relatorio Mensal":
    st.header("Fechamento Mensal por Empresa Atendida")
    st.caption(
        "Total de entrega e coleta por empresa atendida no mes, e quanto isso representa "
        "sobre o total de despesa de frete do mes (soma de todas as despesas, todas as viagens)."
    )
    empresa_nome = st.selectbox("Empresa", list(mapa_empresas.keys()), key="mes_empresa")
    empresa_id = mapa_empresas[empresa_nome]

    hoje = date.today()
    col1, col2 = st.columns(2)
    with col1:
        ano = st.number_input("Ano", min_value=2020, max_value=2100, value=hoje.year, step=1)
    with col2:
        mes = st.number_input("Mes", min_value=1, max_value=12, value=hoje.month, step=1)
    prefixo_mes = f"{int(ano):04d}-{int(mes):02d}"

    viagens = db.listar_viagens(empresa_id=empresa_id)
    despesas_mes = []
    cargas_mes = []
    for v in viagens:
        despesas_mes += [d for d in db.listar_despesas(viagem_id=v["id"]) if d["data"].startswith(prefixo_mes)]
        cargas_mes += [c for c in db.listar_cargas(viagem_id=v["id"]) if c["data"].startswith(prefixo_mes)]

    viagens_mes = [v for v in viagens if v["data_inicio"].startswith(prefixo_mes)]
    viagens_com_despesas = [(v, db.listar_despesas(viagem_id=v["id"])) for v in viagens_mes]

    if not despesas_mes and not cargas_mes:
        st.info(f"Nenhuma despesa ou carga lancada em {prefixo_mes} pra {empresa_nome}.")
    else:
        m = analisar_mes(despesas_mes, cargas_mes)
        c1, c2, c3 = st.columns(3)
        c1.metric("Valor do frete (despesa total do mes)", f"R$ {fmt_numero(m['total_despesa_mes'])}")
        c2.metric("Valor total da receita (entrega+coleta)", f"R$ {fmt_numero(m['total_receita_mes'])}")
        c3.metric(
            "Percentagem do frete sobre a receita",
            f"{fmt_numero(m['percentual_despesa_sobre_receita'], 3)}%"
            if m["percentual_despesa_sobre_receita"] is not None else "-",
        )

        st.subheader("Por empresa atendida -- rateio da despesa pela receita")
        st.caption(
            "A despesa total do mes e alocada a cada empresa proporcional a quanto ela representa "
            "do faturamento (entrega+coleta) do mes -- em valor (R$) e em percentual sobre a receita dela."
        )
        for emp, dd in sorted(m["por_empresa"].items(), key=lambda x: -x[1]["total"]):
            cc1, cc2, cc3, cc4, cc5, cc6 = st.columns([3, 2, 2, 2, 2, 2])
            cc1.write(f"**{emp}**")
            cc2.write(f"Entrega: R\\$ {fmt_numero(dd['entrega'])}")
            cc3.write(f"Coleta: R\\$ {fmt_numero(dd['coleta'])}")
            cc4.write(f"Receita: R\\$ {fmt_numero(dd['total'])}")
            cc5.write(
                f"Despesa alocada: R\\$ {fmt_numero(dd['despesa_alocada'])}"
                if dd["despesa_alocada"] is not None else "-"
            )
            cc6.write(
                f"{fmt_numero(dd['percentual_despesa_sobre_receita'], 3)}% da receita dela"
                if dd["percentual_despesa_sobre_receita"] is not None else "-"
            )

        consumo = analisar_consumo_mes(viagens_com_despesas)
        st.subheader("Media de consumo no mes")
        st.caption(
            "Km rodado e litros abastecidos somados por veiculo/motorista no mes, com a media (km/L) resultante. "
            "So entram viagens com hodometro final e litros lancados."
        )
        col_vei, col_mot = st.columns(2)
        with col_vei:
            st.write("**Por veiculo**")
            if consumo["por_veiculo"]:
                for placa, d in sorted(consumo["por_veiculo"].items(), key=lambda x: x[0]):
                    st.write(
                        f"- **{placa}**: {fmt_numero(d['km'], 0)} km / {fmt_numero(d['litros'])} L "
                        f"→ {fmt_numero(d['consumo_medio']) if d['consumo_medio'] is not None else '-'} km/L "
                        f"({d['viagens']} viagem(ns))"
                    )
            else:
                st.caption("Nenhuma viagem com hodometro final e litros lancados nesse mes.")
        with col_mot:
            st.write("**Por motorista**")
            if consumo["por_motorista"]:
                for nome, d in sorted(consumo["por_motorista"].items(), key=lambda x: x[0]):
                    st.write(
                        f"- **{nome}**: {fmt_numero(d['km'], 0)} km / {fmt_numero(d['litros'])} L "
                        f"→ {fmt_numero(d['consumo_medio']) if d['consumo_medio'] is not None else '-'} km/L "
                        f"({d['viagens']} viagem(ns))"
                    )
            else:
                st.caption("Nenhuma viagem com hodometro final e litros lancados nesse mes.")

# --------------------------------------------------------------- Relatorio Excel
elif pagina == "Relatorio Excel":
    st.header("Gerar Relatorio Excel")
    filtro = st.selectbox("Empresa", ["Todas"] + list(mapa_empresas.keys()))
    empresa_id = None if filtro == "Todas" else mapa_empresas[filtro]
    if st.button("Gerar relatorio"):
        caminho = gerar_relatorio(empresa_id=empresa_id)
        st.success(f"Relatorio gerado: {caminho}")
        with open(caminho, "rb") as f:
            st.download_button(
                "Baixar Excel", data=f.read(),
                file_name=caminho.split("\\")[-1],
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

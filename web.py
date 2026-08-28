"""Interface web do ViaGestão, pronta para hospedagem WSGI."""
import os, tempfile, uuid
from datetime import date
from functools import wraps
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for, send_file
import database as db
from relatorio import gerar_relatorio
from utils import fmt_placa
from analise import analisar_consumo_mes, analisar_mes, analisar_viagem

app = Flask(__name__, static_folder="public", static_url_path="/static")
app.config.update(SECRET_KEY=os.environ.get("VIAGESTAO_SECRET", "desenvolvimento-local-altere-em-producao"), MAX_CONTENT_LENGTH=10 * 1024 * 1024)
app.jinja_env.filters["placa"] = fmt_placa
db.inicializar()

def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"): return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapped

def context():
    empresas=db.listar_empresas(session["user_id"])
    empresa_id=int(request.args.get("empresa",session.get("empresa_id",empresas[0]["id"])))
    if not db.usuario_tem_empresa(session["user_id"],empresa_id): empresa_id=empresas[0]["id"]
    session["empresa_id"]=empresa_id
    return empresas,empresa_id,next(e for e in empresas if e["id"]==empresa_id)

def numero(valor, padrao=0.0):
    """Aceita números digitados no padrão brasileiro sem perder a validação."""
    texto=(valor or "").strip()
    # Campo number envia 502.73; a digitação brasileira normalmente é 502,73
    # ou 1.502,73. Tratamos ambos sem alterar a escala do valor.
    if "," in texto:
        texto=texto.replace(".", "").replace(",", ".")
    return float(texto) if texto else padrao

def viagens_da_empresa(empresa_id):
    return db.listar_viagens(empresa_id)

@app.route("/login",methods=["GET","POST"])
def login():
    if request.method=="POST":
        user=db.autenticar(request.form["email"],request.form["senha"])
        if user:
            session.clear();session.update(user_id=user["id"],nome=user["nome"],perfil=user["perfil"])
            db.auditar(user["id"],None,"Login","Usuário",user["id"])
            return redirect(url_for("dashboard"))
        flash("E-mail ou senha inválidos.","error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    if session.get("user_id"): db.auditar(session["user_id"],session.get("empresa_id"),"Logout","Usuário",session["user_id"])
    session.clear();return redirect(url_for("login"))

@app.route("/")
@login_required
def dashboard():
    empresas,eid,empresa=context(); resumo=db.resumo_dashboard(eid); despesas=resumo["despesas"]
    categories={}
    for x in despesas: categories[x["categoria"]]=categories.get(x["categoria"],0)+x["valor"]
    return render_template("dashboard.html",empresas=empresas,empresa=empresa,resumo=resumo,categories=categories)

@app.route("/viagens",methods=["GET","POST"])
@login_required
def viagens():
    empresas,eid,empresa=context(); motoristas=db.listar_motoristas(eid);veiculos=db.listar_veiculos(eid)
    if request.method=="POST":
        try:
            ident=db.criar_viagem(empresa_id=eid,motorista_id=int(request.form["motorista"]),veiculo_id=int(request.form["veiculo"]),data_inicio=request.form["data_inicio"],data_fim=None,origem=request.form["origem"],destino=request.form["destino"],motivo=request.form.get("motivo"),cliente_atividade=request.form.get("cliente"),hodometro_inicio=numero(request.form.get("km")),hodometro_fim=None,media_computador_bordo=None,valor_adiantamento=numero(request.form.get("adiantamento")),observacoes=request.form.get("observacoes"),status="Em andamento")
            db.auditar(session["user_id"],eid,"Criação","Viagem",ident);flash("Viagem registrada com sucesso.","success")
        except (ValueError,KeyError): flash("Confira os dados obrigatórios da viagem.","error")
        return redirect(url_for("viagens"))
    return render_template("viagens.html",empresas=empresas,empresa=empresa,viagens=viagens_da_empresa(eid),motoristas=motoristas,veiculos=veiculos,hoje=date.today().isoformat())

@app.route("/atualizar-viagem", methods=["GET", "POST"])
@login_required
def atualizar_viagem():
    empresas,eid,empresa=context(); viagens=viagens_da_empresa(eid)
    escolhida=next((x for x in viagens if x["id"]==request.args.get("viagem",type=int)), viagens[0] if viagens else None)
    if request.method=="POST":
        try:
            viagem_id=int(request.form["viagem"])
            if not any(x["id"]==viagem_id for x in viagens): raise ValueError
            db.atualizar_viagem(viagem_id, data_fim=request.form["data_fim"], hodometro_fim=numero(request.form.get("km_final")), media_computador_bordo=numero(request.form.get("media"),None), valor_devolvido=numero(request.form.get("devolvido")), status=request.form["status"], observacoes=request.form.get("observacoes"))
            db.auditar(session["user_id"],eid,"Atualização","Viagem",viagem_id); flash("Viagem atualizada.","success")
        except (ValueError,KeyError): flash("Confira os dados de fechamento.","error")
        return redirect(url_for("atualizar_viagem"))
    analise=analisar_viagem(escolhida,db.listar_despesas(escolhida["id"]),db.listar_cargas(escolhida["id"])) if escolhida else None
    return render_template("atualizar_viagem.html",empresas=empresas,empresa=empresa,viagens=viagens,viagem=escolhida,analise=analise,hoje=date.today().isoformat())

@app.route("/despesas",methods=["GET","POST"])
@login_required
def despesas():
    empresas,eid,empresa=context(); viagens=db.listar_viagens(eid)
    if request.method=="POST":
        try:
            viagem_id=int(request.form["viagem"])
            if not any(x["id"]==viagem_id for x in viagens): raise ValueError
            ident=db.criar_despesa(viagem_id=viagem_id,categoria=request.form["categoria"],data=request.form["data"],valor=numero(request.form["valor"]),litros=numero(request.form.get("litros"),None),local_abastecimento=request.form.get("local"),descricao=request.form.get("descricao"),estabelecimento=request.form.get("estabelecimento"),forma_pagamento=request.form.get("forma"),quilometragem=numero(request.form.get("quilometragem"),None),criado_por=session["user_id"])
            db.auditar(session["user_id"],eid,"Criação","Despesa",ident);flash("Despesa enviada para aprovação.","success")
        except (ValueError,KeyError): flash("Confira os dados da despesa.","error")
        return redirect(url_for("despesas"))
    return render_template("despesas.html",empresas=empresas,empresa=empresa,despesas=db.listar_despesas(empresa_id=eid),viagens=viagens,categorias=["COMBUSTIVEL","PEDAGIO","REFEICAO","DIARIA","HOSPEDAGEM","ESTACIONAMENTO","MANUTENCAO","LAVAGEM","TRANSPORTE","OUTRAS"],hoje=date.today().isoformat())

@app.post("/despesas/<int:despesa_id>/<acao>")
@login_required
def acao_despesa(despesa_id,acao):
    return _processar_acao_despesa(despesa_id,acao)

def _processar_acao_despesa(despesa_id, acao):
    empresas,eid,empresa=context()
    despesa=next((x for x in db.listar_despesas(empresa_id=eid) if x["id"]==despesa_id),None)
    if not despesa: flash("Despesa não encontrada nesta empresa.","error")
    elif session["perfil"] not in ("Administrador","Gestor","Financeiro"): flash("Você não tem permissão para aprovar despesas.","error")
    elif acao=="aprovar": db.alterar_status_despesa(despesa_id,"Aprovada");db.auditar(session["user_id"],eid,"Aprovação","Despesa",despesa_id);flash("Despesa aprovada.","success")
    elif acao=="reprovar": db.alterar_status_despesa(despesa_id,"Reprovada",request.form.get("motivo"));db.auditar(session["user_id"],eid,"Reprovação","Despesa",despesa_id);flash("Despesa reprovada.","success")
    else: flash("Ação de despesa inválida.","error")
    return redirect(url_for("despesas"))

@app.post("/despesas/aprovar/<int:despesa_id>")
@login_required
def aprovar_despesa(despesa_id):
    """URL explícita para os botões — evita ambiguidades em proxies do deploy."""
    return _processar_acao_despesa(despesa_id,"aprovar")

@app.post("/despesas/reprovar/<int:despesa_id>")
@login_required
def reprovar_despesa(despesa_id):
    return _processar_acao_despesa(despesa_id,"reprovar")

@app.post("/despesas/<int:despesa_id>/excluir")
@login_required
def excluir_despesa(despesa_id):
    empresas,eid,empresa=context()
    despesa=next((x for x in db.listar_despesas(empresa_id=eid) if x["id"]==despesa_id),None)
    if not despesa: flash("Despesa não encontrada nesta empresa.","error")
    elif session["perfil"] not in ("Administrador","Gestor","Financeiro") and despesa["criado_por"]!=session["user_id"]: flash("Você não pode excluir esta despesa.","error")
    else: db.excluir_despesa(despesa_id); db.auditar(session["user_id"],eid,"Exclusão","Despesa",despesa_id); flash("Despesa excluída.","success")
    return redirect(url_for("despesas"))

@app.route("/cargas", methods=["GET", "POST"])
@login_required
def cargas():
    empresas,eid,empresa=context(); viagens=viagens_da_empresa(eid)
    viagem_id=request.args.get("viagem",type=int) or (viagens[0]["id"] if viagens else None)
    if request.method=="POST":
        try:
            viagem_id=int(request.form["viagem"])
            if not any(x["id"]==viagem_id for x in viagens): raise ValueError
            ident=db.criar_carga(viagem_id=viagem_id,empresa_cliente=request.form["cliente"].strip(),tipo=request.form["tipo"],data=request.form["data"],valor=numero(request.form["valor"]),descricao=request.form.get("descricao"))
            db.auditar(session["user_id"],eid,"Criação","Carga",ident); flash("Carga lançada.","success")
        except (ValueError,KeyError): flash("Confira os dados da carga.","error")
        return redirect(url_for("cargas",viagem=request.form.get("viagem")))
    return render_template("cargas.html",empresas=empresas,empresa=empresa,viagens=viagens,viagem_id=viagem_id,cargas=db.listar_cargas(viagem_id),hoje=date.today().isoformat())

@app.post("/cargas/<int:carga_id>/excluir")
@login_required
def excluir_carga(carga_id):
    empresas,eid,empresa=context(); viagem_id=request.form.get("viagem",type=int)
    if session["perfil"] not in ("Administrador","Gestor","Financeiro"): flash("Você não tem permissão para excluir cargas.","error")
    else: db.excluir_carga(carga_id); db.auditar(session["user_id"],eid,"Exclusão","Carga",carga_id); flash("Carga excluída.","success")
    return redirect(url_for("cargas",viagem=viagem_id))

@app.get("/consultar-viagens")
@login_required
def consultar_viagens():
    empresas,eid,empresa=context(); todas_viagens=viagens_da_empresa(eid)
    tamanho=request.args.get("por_pagina",10,type=int)
    if tamanho not in (5,10,20): tamanho=10
    total=len(todas_viagens); paginas=max(1,(total+tamanho-1)//tamanho)
    pagina=max(1,min(request.args.get("pagina",1,type=int),paginas))
    viagem_id=request.args.get("viagem",type=int)
    escolhida=next((x for x in todas_viagens if x["id"]==viagem_id),None)
    # Ao entrar na consulta, abre a mais recente; a seleção seguinte preserva
    # a página atual sem renderizar a lista inteira de viagens.
    if escolhida is None and todas_viagens: escolhida=todas_viagens[0]
    inicio=(pagina-1)*tamanho; viagens=todas_viagens[inicio:inicio+tamanho]
    detalhes=None
    if escolhida:
        despesas=db.listar_despesas(escolhida["id"]); cargas_viagem=db.listar_cargas(escolhida["id"])
        detalhes=analisar_viagem(escolhida,despesas,cargas_viagem)
    return render_template("consultar_viagens.html",empresas=empresas,empresa=empresa,viagens=viagens,viagem=escolhida,despesas=despesas if escolhida else [],cargas=cargas_viagem if escolhida else [],detalhes=detalhes,pagina=pagina,paginas=paginas,por_pagina=tamanho,total_viagens=total)

@app.get("/relatorio-mensal")
@login_required
def relatorio_mensal():
    empresas,eid,empresa=context(); hoje=date.today(); ano=request.args.get("ano",hoje.year,type=int); mes=request.args.get("mes",hoje.month,type=int); prefixo=f"{ano:04d}-{mes:02d}"
    viagens=[v for v in viagens_da_empresa(eid) if str(v["data_inicio"]).startswith(prefixo)]
    despesas=[d for d in db.listar_despesas(empresa_id=eid) if str(d["data"]).startswith(prefixo)]
    cargas_mes=[]
    for v in viagens: cargas_mes.extend([c for c in db.listar_cargas(v["id"]) if str(c["data"]).startswith(prefixo)])
    dados=analisar_mes(despesas,cargas_mes)
    consumo=analisar_consumo_mes([(v,db.listar_despesas(v["id"])) for v in viagens])
    return render_template("relatorio_mensal.html",empresas=empresas,empresa=empresa,ano=ano,mes=mes,dados=dados,consumo=consumo,viagens=viagens)

@app.route("/cadastros/<tipo>")
@login_required
def cadastros(tipo):
    if tipo not in ("motoristas","veiculos"): return redirect(url_for("dashboard"))
    empresas,eid,empresa=context(); dados=db.listar_motoristas(eid) if tipo=="motoristas" else db.listar_veiculos(eid)
    return render_template("cadastros.html",empresas=empresas,empresa=empresa,tipo=tipo,dados=dados,motoristas=db.listar_motoristas(eid))

@app.get("/motoristas")
@login_required
def acesso_motoristas():
    return redirect(url_for("cadastros",tipo="motoristas",empresa=request.args.get("empresa")))

@app.get("/veiculos")
@login_required
def acesso_veiculos():
    return redirect(url_for("cadastros",tipo="veiculos",empresa=request.args.get("empresa")))

@app.post("/cadastros/<tipo>")
@login_required
def cadastrar(tipo):
    empresas,eid,empresa=context()
    if session["perfil"] != "Administrador": flash("Apenas administradores podem alterar cadastros.","error"); return redirect(url_for("cadastros",tipo=tipo))
    try:
        if tipo=="motoristas":
            db.criar_motorista(nome=request.form["nome"],codigo=request.form.get("codigo"),cpf=request.form.get("cpf"),telefone=request.form.get("telefone"),email=request.form.get("email"),cnh=request.form.get("cnh"),categoria_cnh=request.form.get("categoria_cnh"),validade_cnh=request.form.get("validade_cnh") or None,status=request.form.get("status","Ativo"),observacoes=request.form.get("observacoes"),empresa_id=eid)
        elif tipo=="veiculos":
            placa="".join(c for c in request.form["placa"].upper() if c.isalnum())
            if len(placa)!=7: raise ValueError("Informe uma placa válida com 7 caracteres.")
            db.criar_veiculo(placa=placa,codigo=request.form.get("codigo"),descricao=request.form.get("modelo"),marca=request.form.get("marca"),ano=int(request.form["ano"]) if request.form.get("ano") else None,tipo=request.form.get("tipo"),quilometragem=numero(request.form.get("quilometragem")),status=request.form.get("status","Ativo"),motorista_id=int(request.form["motorista_id"]) if request.form.get("motorista_id") else None,empresa_id=eid)
        else: raise ValueError("Cadastro inválido.")
        flash("Cadastro realizado com sucesso.","success")
    except (ValueError, KeyError) as e: flash(str(e) or "Confira os dados informados.","error")
    return redirect(url_for("cadastros",tipo=tipo))

@app.post("/cadastros/<tipo>/<int:registro_id>/excluir")
@login_required
def excluir_cadastro(tipo,registro_id):
    empresas,eid,empresa=context()
    if session["perfil"] != "Administrador": flash("Apenas administradores podem excluir cadastros.","error")
    else:
        try:
            if tipo=="motoristas": db.excluir_motorista(registro_id)
            elif tipo=="veiculos": db.excluir_veiculo(registro_id)
            else: raise ValueError("Cadastro inválido.")
            flash("Registro excluído.","success")
        except ValueError as e: flash(str(e),"error")
    return redirect(url_for("cadastros",tipo=tipo,empresa=eid))

@app.route("/cadastros/<tipo>/<int:registro_id>/editar",methods=["GET","POST"])
@login_required
def editar_cadastro(tipo,registro_id):
    empresas,eid,empresa=context()
    if session["perfil"] != "Administrador": flash("Apenas administradores podem alterar cadastros.","error");return redirect(url_for("cadastros",tipo=tipo))
    dados=db.listar_motoristas(eid) if tipo=="motoristas" else db.listar_veiculos(eid)
    registro=next((x for x in dados if x["id"]==registro_id),None)
    if not registro: flash("Registro não encontrado nesta empresa.","error");return redirect(url_for("cadastros",tipo=tipo))
    if request.method=="POST":
        try:
            if tipo=="motoristas": db.atualizar_motorista(registro_id,nome=request.form["nome"],codigo=request.form.get("codigo"),cpf=request.form.get("cpf"),telefone=request.form.get("telefone"),email=request.form.get("email"),cnh=request.form.get("cnh"),categoria_cnh=request.form.get("categoria_cnh"),validade_cnh=request.form.get("validade_cnh") or None,status=request.form.get("status","Ativo"),observacoes=request.form.get("observacoes"))
            elif tipo=="veiculos":
                placa="".join(c for c in request.form["placa"].upper() if c.isalnum())
                if len(placa)!=7: raise ValueError("Informe uma placa válida com 7 caracteres.")
                db.atualizar_veiculo(registro_id,placa=placa,codigo=request.form.get("codigo"),marca=request.form.get("marca"),descricao=request.form.get("modelo"),ano=int(request.form["ano"]) if request.form.get("ano") else None,tipo=request.form.get("tipo"),quilometragem=numero(request.form.get("quilometragem")),motorista_id=int(request.form["motorista_id"]) if request.form.get("motorista_id") else None,status=request.form["status"])
            else: raise ValueError("Cadastro inválido.")
            flash("Cadastro atualizado com sucesso.","success")
        except (ValueError,KeyError) as e: flash(str(e) or "Confira os dados informados.","error")
        return redirect(url_for("cadastros",tipo=tipo,empresa=eid))
    return render_template("editar_cadastro.html",empresas=empresas,empresa=empresa,tipo=tipo,registro=registro,motoristas=db.listar_motoristas(eid))

@app.route("/usuarios",methods=["GET","POST"])
@login_required
def usuarios():
    empresas,eid,empresa=context()
    if session["perfil"] != "Administrador": flash("Acesso restrito a administradores.","error");return redirect(url_for("dashboard"))
    if request.method=="POST":
        try:
            db.criar_usuario(request.form["nome"],request.form["email"],request.form["senha"],request.form["perfil"],[int(x) for x in request.form.getlist("empresas")])
            flash("Usuário cadastrado com sucesso.","success")
        except Exception: flash("Não foi possível cadastrar. Confira e-mail, senha e empresas.","error")
        return redirect(url_for("usuarios"))
    return render_template("usuarios.html",empresas=empresas,empresa=empresa,usuarios=db.listar_usuarios(),perfis=db.PERFIS)

@app.post("/usuarios/<int:usuario_id>/excluir")
@login_required
def excluir_usuario(usuario_id):
    if session["perfil"] != "Administrador" or usuario_id==session["user_id"]: flash("Não é permitido excluir este usuário.","error")
    else: db.excluir_usuario(usuario_id);flash("Usuário excluído.","success")
    return redirect(url_for("usuarios"))

@app.get("/excel")
@app.get("/relatorios/excel")
@login_required
def exportar_excel():
    empresas,eid,empresa=context()
    # Em funções Vercel apenas /tmp é gravável; localmente também funciona.
    caminho=os.path.join(tempfile.gettempdir(),f"relatorio_{empresa['nome'].lower()}_{uuid.uuid4().hex}.xlsx")
    gerar_relatorio(empresa_id=eid,caminho_saida=caminho)
    return send_file(caminho,as_attachment=True,download_name=f"relatorio_{empresa['nome'].lower()}.xlsx")

@app.get("/relatorios")
@login_required
def relatorios():
    empresas,eid,empresa=context()
    return render_template("relatorios.html",empresas=empresas,empresa=empresa)

if __name__ == "__main__": app.run(host="0.0.0.0",port=int(os.environ.get("PORT",8502)),debug=False)

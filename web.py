"""Interface web do ViaGestão, pronta para hospedagem WSGI."""
import os, tempfile, uuid
from datetime import date
from functools import wraps
from flask import Flask, flash, redirect, render_template, request, session, url_for, send_file
import database as db
from relatorio import gerar_relatorio
from utils import fmt_placa

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
            ident=db.criar_viagem(empresa_id=eid,motorista_id=int(request.form["motorista"]),veiculo_id=int(request.form["veiculo"]),data_inicio=request.form["data_inicio"],data_fim=None,origem=request.form["origem"],destino=request.form["destino"],motivo=request.form.get("motivo"),cliente_atividade=request.form.get("cliente"),hodometro_inicio=float(request.form.get("km",0)),hodometro_fim=None,media_computador_bordo=None,observacoes=request.form.get("observacoes"),status="Planejada")
            db.auditar(session["user_id"],eid,"Criação","Viagem",ident);flash("Viagem registrada com sucesso.","success")
        except (ValueError,KeyError): flash("Confira os dados obrigatórios da viagem.","error")
        return redirect(url_for("viagens"))
    return render_template("viagens.html",empresas=empresas,empresa=empresa,viagens=db.listar_viagens(eid),motoristas=motoristas,veiculos=veiculos)

@app.route("/despesas",methods=["GET","POST"])
@login_required
def despesas():
    empresas,eid,empresa=context(); viagens=db.listar_viagens(eid)
    if request.method=="POST":
        try:
            ident=db.criar_despesa(viagem_id=int(request.form["viagem"]),categoria=request.form["categoria"],data=request.form["data"],valor=float(request.form["valor"]),descricao=request.form.get("descricao"),estabelecimento=request.form.get("estabelecimento"),forma_pagamento=request.form.get("forma"),quilometragem=None,criado_por=session["user_id"])
            db.auditar(session["user_id"],eid,"Criação","Despesa",ident);flash("Despesa enviada para aprovação.","success")
        except (ValueError,KeyError): flash("Confira os dados da despesa.","error")
        return redirect(url_for("despesas"))
    return render_template("despesas.html",empresas=empresas,empresa=empresa,despesas=db.listar_despesas(empresa_id=eid),viagens=viagens,categorias=db.CATEGORIAS)

@app.post("/despesas/<int:despesa_id>/<acao>")
@login_required
def acao_despesa(despesa_id,acao):
    empresas,eid,empresa=context()
    if session["perfil"] not in ("Administrador","Gestor","Financeiro"): flash("Você não tem permissão para aprovar despesas.","error")
    elif acao=="aprovar": db.alterar_status_despesa(despesa_id,"Aprovada");db.auditar(session["user_id"],eid,"Aprovação","Despesa",despesa_id);flash("Despesa aprovada.","success")
    elif acao=="reprovar": db.alterar_status_despesa(despesa_id,"Reprovada",request.form.get("motivo"));db.auditar(session["user_id"],eid,"Reprovação","Despesa",despesa_id);flash("Despesa reprovada.","success")
    return redirect(url_for("despesas"))

@app.route("/cadastros/<tipo>")
@login_required
def cadastros(tipo):
    empresas,eid,empresa=context(); dados=db.listar_motoristas(eid) if tipo=="motoristas" else db.listar_veiculos(eid)
    return render_template("cadastros.html",empresas=empresas,empresa=empresa,tipo=tipo,dados=dados)

@app.post("/cadastros/<tipo>")
@login_required
def cadastrar(tipo):
    empresas,eid,empresa=context()
    if session["perfil"] != "Administrador": flash("Apenas administradores podem alterar cadastros.","error"); return redirect(url_for("cadastros",tipo=tipo))
    try:
        if tipo=="motoristas":
            db.criar_motorista(nome=request.form["nome"],codigo=request.form.get("codigo"),cpf=request.form.get("cpf"),telefone=request.form.get("telefone"),email=request.form.get("email"),cnh=request.form.get("cnh"),categoria_cnh=None,validade_cnh=None,status="Ativo",observacoes=None,empresa_id=eid)
        elif tipo=="veiculos":
            placa="".join(c for c in request.form["placa"].upper() if c.isalnum())
            if len(placa)!=7: raise ValueError("Informe uma placa válida com 7 caracteres.")
            db.criar_veiculo(placa=placa,codigo=request.form.get("codigo"),descricao=request.form.get("modelo"),marca=request.form.get("marca"),ano=None,tipo=request.form.get("tipo"),quilometragem=0,status="Ativo",motorista_id=None,empresa_id=eid)
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
    return redirect(url_for("cadastros",tipo=tipo))

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
            if tipo=="motoristas": db.atualizar_motorista(registro_id,nome=request.form["nome"],codigo=request.form.get("codigo"),cpf=request.form.get("cpf"),telefone=request.form.get("telefone"),email=request.form.get("email"),cnh=request.form.get("cnh"))
            elif tipo=="veiculos":
                placa="".join(c for c in request.form["placa"].upper() if c.isalnum())
                if len(placa)!=7: raise ValueError("Informe uma placa válida com 7 caracteres.")
                db.atualizar_veiculo(registro_id,placa=placa,codigo=request.form.get("codigo"),marca=request.form.get("marca"),descricao=request.form.get("modelo"),tipo=request.form.get("tipo"),status=request.form["status"])
            else: raise ValueError("Cadastro inválido.")
            flash("Cadastro atualizado com sucesso.","success")
        except (ValueError,KeyError) as e: flash(str(e) or "Confira os dados informados.","error")
        return redirect(url_for("cadastros",tipo=tipo))
    return render_template("editar_cadastro.html",empresas=empresas,empresa=empresa,tipo=tipo,registro=registro)

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

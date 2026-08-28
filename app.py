import os
from datetime import date
import pandas as pd
import streamlit as st
import database as db

st.set_page_config(page_title="ViaGestão", page_icon="✦", layout="wide", initial_sidebar_state="expanded")
db.inicializar()

st.markdown("""<style>
:root{--blue:#075ea8;--orange:#ff8200;--ink:#10243d;--muted:#66788d;--line:#e8eef4}
.stApp{background:#f6f8fb;color:var(--ink)} [data-testid=stSidebar]{background:linear-gradient(180deg,#073d70,#075ea8)} [data-testid=stSidebar] *{color:#fff!important}
.hero{padding:1.8rem 2rem;border-radius:20px;background:linear-gradient(120deg,#073d70,#0876c7);color:white;margin-bottom:1.25rem;box-shadow:0 12px 28px #0b4f8130}.hero h1{margin:0;font-size:2rem}.hero p{margin:.3rem 0 0;color:#d7edff}
[data-testid=stMetric]{background:#fff;border:1px solid var(--line);border-radius:14px;padding:15px;box-shadow:0 4px 12px #10243d0a}.stButton>button{border-radius:9px;border:0;background:var(--blue);color:#fff;font-weight:600}.badge{padding:4px 10px;border-radius:99px;font-size:.78rem;font-weight:700}.login-card{max-width:470px;margin:5vh auto;padding:2.4rem;border-radius:22px;background:white;box-shadow:0 18px 60px #0d315229}
</style>""",unsafe_allow_html=True)

ROOT=os.path.dirname(__file__); LOGO=os.path.join(ROOT,"assets","erimax-logo.png")
def money(v): return f"R$ {float(v or 0):,.2f}".replace(",","X").replace(".",",").replace("X",".")
def ok_role(*roles): return st.session_state.user["perfil"] in roles
def flash(msg): st.toast(msg,icon="✅")

def login():
 st.markdown('<div class="login-card">',unsafe_allow_html=True)
 c1,c2=st.columns([1,3]);
 with c1: st.image(LOGO,width=68)
 with c2: st.markdown("### ViaGestão\nControle de viagens e despesas")
 st.caption("Acesse sua conta corporativa para continuar.")
 with st.form("login"):
  email=st.text_input("E-mail",placeholder="nome@empresa.com")
  senha=st.text_input("Senha",type="password")
  entered=st.form_submit_button("Entrar",use_container_width=True)
 if entered:
  u=db.autenticar(email,senha)
  if u: st.session_state.user=dict(u); db.auditar(u['id'],None,"Login","Usuário",u['id']);st.rerun()
  else: st.error("E-mail ou senha inválidos.")
 st.caption("Primeiro acesso: **admin@viagens.local** · senha **admin123**")
 st.markdown("</div>",unsafe_allow_html=True)

if "user" not in st.session_state:
 login();st.stop()
u=st.session_state.user; empresas=db.listar_empresas(u['id'])
if not empresas: st.error("Sua conta não possui empresas vinculadas.");st.stop()
if "empresa" not in st.session_state or not db.usuario_tem_empresa(u['id'],st.session_state.empresa):st.session_state.empresa=empresas[0]['id']

with st.sidebar:
 st.image(LOGO,width=146); st.caption("GESTÃO DE VIAGENS")
 nomes={x['id']:x['nome'] for x in empresas}; eid=st.selectbox("Empresa ativa",list(nomes),format_func=lambda x:nomes[x],index=list(nomes).index(st.session_state.empresa))
 st.session_state.empresa=eid
 page=st.radio("Menu",["Dashboard","Viagens","Despesas","Motoristas","Veículos","Relatórios","Administração"])
 st.divider();st.caption(f"{u['nome']} · {u['perfil']}")
 if st.button("Sair",use_container_width=True): db.auditar(u['id'],eid,"Logout","Usuário",u['id']);del st.session_state.user;st.rerun()

empresa=nomes[eid]
def header(title,subtitle):st.markdown(f'<section class="hero"><h1>{title}</h1><p>{subtitle}</p></section>',unsafe_allow_html=True)
def table(data,cols=None):
 if not data:st.info("Nenhum registro encontrado com os filtros informados.");return
 frame=pd.DataFrame([dict(x) for x in data]);st.dataframe(frame[cols] if cols else frame,use_container_width=True,hide_index=True)

if page=="Dashboard":
 header("Visão executiva",f"Indicadores consolidados · {empresa}")
 r=db.resumo_dashboard(eid); metrics=[("Despesas aprovadas",money(r['total'])),("Pendentes",money(r['pendente'])),("Reprovadas",money(r['reprovada'])),("Viagens",r['viagens']),("Motoristas ativos",r['motoristas']),("Custo médio/viagem",money(r['media_viagem'])),("Custo médio/motorista",money(r['media_motorista']))]
 for i in range(0,len(metrics),4):
  for col,(label,val) in zip(st.columns(4),metrics[i:i+4]):col.metric(label,val)
 ds=r['despesas'];
 st.subheader("Despesas por categoria")
 if ds:
  df=pd.DataFrame([dict(x) for x in ds]);st.bar_chart(df.groupby('categoria')['valor'].sum())
  a,b=st.columns(2)
  with a:st.subheader("Por motorista");st.bar_chart(df.groupby('motorista_nome')['valor'].sum())
  with b:st.subheader("Evolução por período");st.line_chart(df.groupby('data')['valor'].sum())
 else:st.info("Cadastre viagens e despesas para visualizar os gráficos.")

elif page=="Motoristas":
 header("Motoristas","Cadastro e controle da equipe de campo")
 if ok_role("Administrador"):
  with st.expander("+ Novo motorista"):
   with st.form("motorista"):
    a,b,c=st.columns(3);nome=a.text_input("Nome completo");cpf=b.text_input("CPF");tel=c.text_input("Telefone");email=a.text_input("E-mail");cnh=b.text_input("CNH");cat=c.text_input("Categoria CNH");valid=a.date_input("Validade da CNH",value=None);status=b.selectbox("Status",["Ativo","Inativo"]);obs=st.text_area("Observações");save=st.form_submit_button("Salvar motorista")
   if save:
    if not nome:st.error("Informe o nome completo.")
    else: db.criar_motorista(nome=nome,codigo=None,cpf=cpf,telefone=tel,email=email,cnh=cnh,categoria_cnh=cat,validade_cnh=str(valid) if valid else None,status=status,observacoes=obs,empresa_id=eid);flash("Motorista cadastrado com sucesso.");st.rerun()
 table(db.listar_motoristas(eid),["nome","cpf","telefone","cnh","validade_cnh","status"])

elif page=="Veículos":
 header("Veículos","Frota vinculada à empresa selecionada")
 motoristas=db.listar_motoristas(eid)
 if ok_role("Administrador"):
  with st.expander("+ Novo veículo"):
   with st.form("veiculo"):
    a,b,c=st.columns(3);placa=a.text_input("Placa").upper();marca=b.text_input("Marca");modelo=c.text_input("Modelo");ano=a.number_input("Ano",1900,2100,value=2026);tipo=b.text_input("Tipo");km=c.number_input("Quilometragem atual",min_value=0.0);motor=a.selectbox("Motorista principal",[None]+[x['id'] for x in motoristas],format_func=lambda x:"Não definido" if x is None else next(m['nome'] for m in motoristas if m['id']==x));status=b.selectbox("Status",["Ativo","Manutenção","Inativo"]);save=st.form_submit_button("Salvar veículo")
   if save:
    if not placa:st.error("Informe a placa.")
    else:db.criar_veiculo(placa=placa,codigo=None,descricao=modelo,marca=marca,ano=ano,tipo=tipo,quilometragem=km,status=status,motorista_id=motor,empresa_id=eid);flash("Veículo cadastrado com sucesso.");st.rerun()
 table(db.listar_veiculos(eid),["placa","marca","descricao","ano","tipo","quilometragem","status","motorista_nome"])

elif page=="Viagens":
 header("Viagens",f"Planejamento, operação e custo · {empresa}")
 ms=db.listar_motoristas(eid);vs=db.listar_veiculos(eid)
 if ok_role("Administrador","Gestor"):
  with st.expander("+ Nova viagem"):
   with st.form("viagem"):
    a,b,c=st.columns(3);motor=a.selectbox("Motorista",[x['id'] for x in ms],format_func=lambda x:next(m['nome'] for m in ms if m['id']==x)) if ms else None;veic=b.selectbox("Veículo",[x['id'] for x in vs],format_func=lambda x:next(v['placa'] for v in vs if v['id']==x)) if vs else None;saida=c.date_input("Saída",date.today());origem=a.text_input("Origem");destino=b.text_input("Destino");motivo=c.text_input("Motivo");cliente=a.text_input("Cliente/atividade");km=b.number_input("KM inicial",min_value=0.0);status=c.selectbox("Status",db.STATUS_VIAGEM);obs=st.text_area("Observações");save=st.form_submit_button("Registrar viagem")
   if save:
    if not motor or not veic or not origem or not destino:st.error("Preencha motorista, veículo, origem e destino.")
    else:i=db.criar_viagem(empresa_id=eid,motorista_id=motor,veiculo_id=veic,data_inicio=str(saida),data_fim=None,origem=origem,destino=destino,motivo=motivo,cliente_atividade=cliente,hodometro_inicio=km,hodometro_fim=None,media_computador_bordo=None,observacoes=obs,status=status);db.auditar(u['id'],eid,"Criação","Viagem",i);flash("Viagem registrada com sucesso.");st.rerun()
 viagens=db.listar_viagens(eid);table(viagens,["id","data_inicio","motorista_nome","veiculo_placa","origem","destino","motivo","status"])
 if viagens:
  v=st.selectbox("Detalhar viagem",[x['id'] for x in viagens],format_func=lambda x:f"Viagem #{x}")
  trip=db.obter_viagem(v);des=db.listar_despesas(viagem_id=v);valid=[x for x in des if x['status'] in ('Aprovada','Paga')];total=sum(x['valor'] for x in valid);kmr=(trip['hodometro_fim'] or trip['hodometro_inicio'])-trip['hodometro_inicio'];a,b,c=st.columns(3);a.metric("Custo aprovado",money(total));b.metric("Quilômetros",f"{kmr:,.0f} km");c.metric("Custo por KM",money(total/kmr) if kmr else "—");table(des,["data","categoria","descricao","valor","status"])

elif page=="Despesas":
 header("Despesas de viagem","Lançamento, aprovação e pagamento")
 trips=db.listar_viagens(eid);status_filter=st.selectbox("Filtrar por status",["Todos"]+db.STATUS_DESPESA);status=None if status_filter=="Todos" else status_filter
 if ok_role("Administrador","Motorista"):
  with st.expander("+ Nova despesa"):
   with st.form("despesa"):
    viagem=st.selectbox("Viagem",[x['id'] for x in trips],format_func=lambda x:f"#{x} · {next(v['origem']+' → '+v['destino'] for v in trips if v['id']==x)}") if trips else None;a,b,c=st.columns(3);data=a.date_input("Data",date.today());cat=b.selectbox("Categoria",db.CATEGORIAS);valor=c.number_input("Valor (R$)",min_value=0.0,step=0.01);est=a.text_input("Estabelecimento");forma=b.selectbox("Forma de pagamento",["Dinheiro","Cartão","PIX","Faturado"]);km=c.number_input("Quilometragem (se aplicável)",min_value=0.0);desc=st.text_area("Descrição");save=st.form_submit_button("Lançar despesa")
   if save:
    if not viagem or not valor:st.error("Informe uma viagem e um valor maior que zero.")
    else:i=db.criar_despesa(viagem_id=viagem,categoria=cat,data=str(data),valor=valor,descricao=desc,estabelecimento=est,forma_pagamento=forma,quilometragem=km,criado_por=u['id']);db.auditar(u['id'],eid,"Criação","Despesa",i);flash("Despesa cadastrada e enviada para aprovação.");st.rerun()
 ds=db.listar_despesas(empresa_id=eid,status=status);table(ds,["id","data","viagem_numero","motorista_nome","categoria","descricao","valor","status"])
 if ds and ok_role("Administrador","Gestor","Financeiro"):
  with st.expander("Aprovar, reprovar ou pagar"):
   did=st.selectbox("Despesa",[x['id'] for x in ds],format_func=lambda x:f"Despesa #{x}");a,b,c=st.columns(3)
   if a.button("Aprovar"):db.alterar_status_despesa(did,"Aprovada");db.auditar(u['id'],eid,"Aprovação","Despesa",did);flash("Despesa aprovada.");st.rerun()
   motivo=b.text_input("Motivo da reprovação")
   if b.button("Reprovar"):db.alterar_status_despesa(did,"Reprovada",motivo);db.auditar(u['id'],eid,"Reprovação","Despesa",did);flash("Despesa reprovada.");st.rerun()
   if c.button("Registrar pagamento"):
    d=next(x for x in ds if x['id']==did)
    try:db.registrar_pagamento(did,str(date.today()),d['valor'],d['forma_pagamento'],u['id'],None);flash("Pagamento registrado.");st.rerun()
    except ValueError as e:st.error(str(e))
 if ds:
  with st.expander("Comprovantes"):
   did=st.selectbox("Despesa para comprovante",[x['id'] for x in ds],format_func=lambda x:f"Despesa #{x}",key="anexo_despesa")
   arquivo=st.file_uploader("Anexar PDF, JPG, JPEG ou PNG",type=["pdf","jpg","jpeg","png"])
   if st.button("Salvar comprovante"):
    if not arquivo:st.error("Selecione um arquivo válido.")
    elif arquivo.size>10*1024*1024:st.error("O comprovante deve ter no máximo 10 MB.")
    else:
     pasta=os.path.join(ROOT,"uploads");os.makedirs(pasta,exist_ok=True);nome=f"{did}_{date.today().isoformat()}_{arquivo.name}";caminho=os.path.join(pasta,nome)
     with open(caminho,"wb") as f:f.write(arquivo.getbuffer())
     db.anexar_comprovante(did,arquivo.name,caminho,arquivo.size,u['id']);flash("Comprovante anexado com sucesso.")
   anexos=db.listar_anexos(did)
   if anexos: table(anexos,["nome","tamanho","criado_em"])

elif page=="Relatórios":
 header("Relatórios",f"Análise financeira · {empresa}")
 ds=db.listar_despesas(empresa_id=eid);table(ds,["data","motorista_nome","categoria","estabelecimento","valor","forma_pagamento","status"])
 if ds:
  df=pd.DataFrame([dict(x) for x in ds]);csv=df.to_csv(index=False).encode("utf-8-sig");st.download_button("Exportar CSV respeitando a empresa selecionada",csv,"relatorio_despesas.csv","text/csv")

else:
 header("Administração","Usuários, permissões e segurança")
 if not ok_role("Administrador"):st.warning("Acesso restrito a administradores.");st.stop()
 a,b=st.columns([1,1]);
 with a:
  st.subheader("Usuários")
  with st.form("usuario"):
   nome=st.text_input("Nome");email=st.text_input("E-mail");senha=st.text_input("Senha inicial",type="password");perfil=st.selectbox("Perfil",db.PERFIS);acesso=st.multiselect("Empresas com acesso",[x['id'] for x in empresas],default=[eid],format_func=lambda x:nomes[x]);save=st.form_submit_button("Criar usuário")
  if save:
   try:db.criar_usuario(nome,email,senha,perfil,acesso);flash("Usuário criado com senha protegida.");st.rerun()
   except Exception:st.error("Não foi possível criar: confira o e-mail e os campos obrigatórios.")
 with b:
  st.subheader("Minha senha")
  with st.form("senha"):
   nova=st.text_input("Nova senha",type="password");change=st.form_submit_button("Alterar senha")
  if change:
   if len(nova)<8:st.error("Use pelo menos 8 caracteres.")
   else:db.alterar_senha(u['id'],nova);flash("Senha alterada com sucesso.")
 table(db.listar_usuarios(),["nome","email","perfil","empresas","ativo"])

import unicodedata


def fmt_data(data_iso: str) -> str:
    """Converte 'AAAA-MM-DD' (formato salvo no banco) para 'DD/MM/AAAA' (exibicao)."""
    if not data_iso:
        return ""
    partes = data_iso.split("-")
    if len(partes) != 3:
        return data_iso
    ano, mes, dia = partes
    return f"{dia}/{mes}/{ano}"


def fmt_codigo(nome_ou_placa: str, codigo: str = None) -> str:
    """Prefixa nome/placa com o codigo cadastrado, se houver.
    Ex: fmt_codigo('Joao', '07') -> '[07] Joao'; sem codigo -> so 'Joao'."""
    if codigo:
        return f"[{codigo}] {nome_ou_placa}"
    return nome_ou_placa


def fmt_placa(placa: str, codigo: str = None) -> str:
    """Exibe placas antigas e Mercosul no padrão AAA-1A11, sem mexer no histórico."""
    limpa = "".join(c for c in (placa or "").upper() if c.isalnum())
    # Correções visuais que também são aplicadas pelo banco ao consolidar frota.
    limpa = {
        "RHW2101": "RHW2I01",
        "RHW2IO1": "RHW2I01",
        "SEB": "SEB8D65",
    }.get(limpa, limpa)
    if len(limpa) == 7:
        limpa = f"{limpa[:3]}-{limpa[3:]}"
    return fmt_codigo(limpa or placa or "", codigo)


def fmt_numero(valor, casas: int = 2) -> str:
    """Formata um numero no padrao BR: virgula decimal, ponto de milhar.
    Ex: 6.0 (casas=3) -> '6,000'; 2000.0 (casas=2) -> '2.000,00'."""
    txt = f"{valor:,.{casas}f}"
    return txt.replace(",", "X").replace(".", ",").replace("X", ".")


def parse_numero(texto: str) -> float:
    """Aceita tanto '1000,00' (virgula decimal, padrao BR) quanto '1000.00'
    (ponto decimal) e tambem milhar '1.234,56'. Levanta ValueError com
    mensagem clara se o texto nao for um numero valido."""
    texto = (texto or "").strip().replace(" ", "")
    if not texto:
        return 0.0
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        raise ValueError(
            f"'{texto}' nao e um numero valido. Use algo como 1000 ou 1000,00."
        )


MOTORISTAS_PADRONIZADOS = {
    "MARK": {
        "IZAIAS MENEZES DA SILVA": "IZAIAS MENEZES DA SILVA",
        "JOVENTINO": "JOVENTINO FRANCISCO SANTOS",
        "JOVENTINO FRANCISCO SANTOS": "JOVENTINO FRANCISCO SANTOS",
        "LUCAS": "LUCAS FERREIRA DOS SANTOS",
        "LUCAS FERREIRA": "LUCAS FERREIRA DOS SANTOS",
        "LUCAS FERREIRA DOS SANTOS": "LUCAS FERREIRA DOS SANTOS",
        "MICHAEL": "MICHAEL RAFAEL PESSOA DOS SANTOS",
        "MICHAEL RAFAEL PESSOA DOS SANTOS": "MICHAEL RAFAEL PESSOA DOS SANTOS",
        "NILTON": "NILTON RODRIGUES PAIS",
        "NILTON RODRIGUES PAZ": "NILTON RODRIGUES PAIS",
        "NILTON RODRIGUES PAIS": "NILTON RODRIGUES PAIS",
    },
    "ERIMAX": {
        "ANDERSON": "ANDERSON ANTONIO FELIZARDO DE SOUZA",
        "ANDERSON ANTONIO FELIZARDO DE SOUZA": "ANDERSON ANTONIO FELIZARDO DE SOUZA",
        "IZAIAS MENEZES DA SILVA": "IZAIAS MENEZES DA SILVA",
        "LUCAS": "LUCAS FERREIRA DOS SANTOS",
        "LUCAS FERREIRA": "LUCAS FERREIRA DOS SANTOS",
        "LUCAS FERREIRA DOS SANTOS": "LUCAS FERREIRA DOS SANTOS",
        "MAYKON": "MAYKON RODRIGO PEREIRA",
        "MAYKON PEREIRA": "MAYKON RODRIGO PEREIRA",
        "MAYKON RODRIGO PEREIRA": "MAYKON RODRIGO PEREIRA",
        "NILTON": "NILTON RODRIGUES PAZ",
        "NILTON PAZ": "NILTON RODRIGUES PAZ",
        "NILTON RODRIGUES PAZ": "NILTON RODRIGUES PAZ",
        "THIAGO": "TIAGO CUSTODIO MARTINS",
        "TIAGO CUSTODIO": "TIAGO CUSTODIO MARTINS",
        "TIAGO CUSTODIO MARTINS": "TIAGO CUSTODIO MARTINS",
    },
}


def chave_texto(valor: str) -> str:
    """Normaliza texto livre para comparação sem acento ou pontuação."""
    texto = (
        unicodedata.normalize("NFKD", valor or "")
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    texto = texto.upper().replace("(MANUTENCAO)", "")
    return " ".join(
        "".join(
            caractere if caractere.isalnum() or caractere == " " else " "
            for caractere in texto
        ).split()
    )


def nome_motorista_padrao(empresa: str, nome: str) -> str:
    """Nome de exibição único para cadastros históricos e planilhas."""
    empresa = (
        "ERIMAX" if (empresa or "").upper() == "ERIMAR" else (empresa or "").upper()
    )
    chave = chave_texto(nome)
    return MOTORISTAS_PADRONIZADOS.get(empresa, {}).get(chave, chave)

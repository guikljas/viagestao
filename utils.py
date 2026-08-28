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
        raise ValueError(f"'{texto}' nao e um numero valido. Use algo como 1000 ou 1000,00.")

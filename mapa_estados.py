"""Rateio de despesas por UF a partir do destino registrado nas viagens."""

import re
import unicodedata

ESTADOS = [
    ("AC", "Acre"),
    ("AL", "Alagoas"),
    ("AP", "Amapá"),
    ("AM", "Amazonas"),
    ("BA", "Bahia"),
    ("CE", "Ceará"),
    ("DF", "Distrito Federal"),
    ("ES", "Espírito Santo"),
    ("GO", "Goiás"),
    ("MA", "Maranhão"),
    ("MT", "Mato Grosso"),
    ("MS", "Mato Grosso do Sul"),
    ("MG", "Minas Gerais"),
    ("PA", "Pará"),
    ("PB", "Paraíba"),
    ("PR", "Paraná"),
    ("PE", "Pernambuco"),
    ("PI", "Piauí"),
    ("RJ", "Rio de Janeiro"),
    ("RN", "Rio Grande do Norte"),
    ("RS", "Rio Grande do Sul"),
    ("RO", "Rondônia"),
    ("RR", "Roraima"),
    ("SC", "Santa Catarina"),
    ("SP", "São Paulo"),
    ("SE", "Sergipe"),
    ("TO", "Tocantins"),
]


def normalizar(texto):
    texto = (
        unicodedata.normalize("NFKD", texto or "")
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return " ".join(texto.upper().split())


NOMES = {normalizar(nome): uf for uf, nome in ESTADOS}
CIDADES = {
    "ASSIS CHATEAUBRIAND": "PR",
    "ASSIS CHATEUBRIAND": "PR",
    "ASSIS CHATE": "PR",
    "ASSIS CHAT": "PR",
    "UMUARAMA": "PR",
    "TOLEDO": "PR",
    "CASCAVEL": "PR",
    "MARINGA": "PR",
    "PRESIDENTE PRUDENTE": "SP",
    "FORMOSA": "GO",
}


def extrair_ufs(texto):
    texto = normalizar(texto)
    encontradas = []
    for nome, uf in NOMES.items():
        if (
            re.search(rf"(?<![A-Z]){re.escape(nome)}(?![A-Z])", texto)
            and uf not in encontradas
        ):
            encontradas.append(uf)
    for cidade, uf in CIDADES.items():
        if (
            re.search(rf"(?<![A-Z]){re.escape(cidade)}(?![A-Z])", texto)
            and uf not in encontradas
        ):
            encontradas.append(uf)
    for uf, _ in ESTADOS:
        if re.search(rf"(?<![A-Z]){uf}(?![A-Z])", texto) and uf not in encontradas:
            encontradas.append(uf)
    return encontradas


def calcular_mapa_estados(viagens, despesas):
    """Retorna dados serializáveis para o mapa, sem duplicar rotas multi-UF."""
    nomes = dict(ESTADOS)
    resultado = {
        uf: {
            "uf": uf,
            "nome": nome,
            "total": 0.0,
            "lancamentos": 0,
            "veiculos": {},
            "motoristas": {},
        }
        for uf, nome in ESTADOS
    }
    por_viagem = {viagem["id"]: viagem for viagem in viagens}
    for despesa in despesas:
        viagem = por_viagem.get(despesa["viagem_id"])
        if not viagem:
            continue
        ufs = extrair_ufs(viagem["destino"]) or extrair_ufs(viagem["origem"])
        if not ufs:
            continue
        valor_rateado = float(despesa["valor"]) / len(ufs)
        for uf in ufs:
            estado = resultado[uf]
            estado["total"] += valor_rateado
            estado["lancamentos"] += 1
            placa = viagem["veiculo_placa"] or "Não informado"
            motorista = viagem["motorista_nome"] or "Não informado"
            estado["veiculos"][placa] = (
                estado["veiculos"].get(placa, 0.0) + valor_rateado
            )
            estado["motoristas"][motorista] = (
                estado["motoristas"].get(motorista, 0.0) + valor_rateado
            )
    for estado in resultado.values():
        estado["total"] = round(estado["total"], 2)
        estado["veiculos"] = [
            {"nome": nome, "valor": round(valor, 2)}
            for nome, valor in sorted(
                estado["veiculos"].items(), key=lambda item: item[1], reverse=True
            )
        ]
        estado["motoristas"] = [
            {"nome": nome, "valor": round(valor, 2)}
            for nome, valor in sorted(
                estado["motoristas"].items(), key=lambda item: item[1], reverse=True
            )
        ]
    return resultado

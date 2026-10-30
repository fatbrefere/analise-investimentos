"""
Análise qualitativa diária escrita pelo Claude.

Para cada ação candidata (consenso + carteira) o modelo recebe os fundamentos,
a posição em cada método, o cenário macro e as manchetes recentes, e devolve
uma análise estruturada: tese, riscos, catalisadores, sensibilidade a
cenários, classificação (oportunidade / estudar / armadilha provável) e
convicção. Também escreve um panorama de mercado e alertas para a carteira.

Uso:
    ANTHROPIC_API_KEY=... python -m investimentos.analise_ia
    python -m investimentos.analise_ia --maximo 20      # menos papéis (mais barato)

Sem a chave, o módulo apenas avisa e sai sem erro, para o pipeline diário
continuar funcionando.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
from datetime import datetime
from typing import Literal

import pandas as pd
from pydantic import BaseModel, Field

from investimentos import config, estrategias
from investimentos.carteira import carregar_carteira
from investimentos.fontes import noticias

log = logging.getLogger("investimentos.analise_ia")

MODELO = os.environ.get("INVESTIMENTOS_MODELO_IA", "claude-opus-5-5")
ARQ_ANALISE = config.PASTA_DADOS / "analise_ia.json"
PAPEIS_POR_CHAMADA = 10
MAXIMO_PADRAO = 30

AVISO = ("Análise gerada automaticamente por inteligência artificial a partir de dados públicos. "
         "Não é recomendação de investimento. Confira as informações antes de decidir.")


# ---------------------------------------------------------------------------
# Esquema da resposta (structured outputs)
# ---------------------------------------------------------------------------
class Sensibilidade(BaseModel):
    juros: int = Field(description="Efeito de QUEDA da Selic/juros no negócio: -2 (muito negativo) a +2 (muito positivo)")
    dolar: int = Field(description="Efeito de ALTA do dólar: -2 a +2")
    commodities: int = Field(description="Efeito de ALTA das commodities: -2 a +2")
    consumo: int = Field(description="Efeito de aquecimento do consumo interno: -2 a +2")
    governo: int = Field(description="Dependência de decisões de governo/regulação: 0 (nenhuma) a 2 (alta); negativo se exposição é risco")


class AnalisePapel(BaseModel):
    ticker: str
    classificacao: Literal["oportunidade", "estudar", "armadilha provável"]
    conviccao: int = Field(description="1 (baixa) a 5 (alta)")
    resumo: str = Field(description="Uma frase: o que a empresa faz e por que aparece barata")
    tese: str = Field(description="Por que pode ser uma boa compra para médio/longo prazo (2 a 4 frases)")
    riscos: list[str] = Field(description="3 a 5 riscos concretos")
    catalisadores: list[str] = Field(description="2 a 4 eventos que podem destravar valor")
    barata_por_que: Literal["ciclo do setor", "problema da empresa", "mercado ignorando", "lucro não recorrente", "juros altos no Brasil", "outro"]
    sensibilidade: Sensibilidade
    o_que_acompanhar: list[str] = Field(description="2 a 3 indicadores ou eventos para monitorar")
    noticias_relevantes: str = Field(description="O que as manchetes recentes mudam na tese, ou 'nada relevante'")


class LoteAnalise(BaseModel):
    papeis: list[AnalisePapel]


class AlertaCarteira(BaseModel):
    ticker: str
    gravidade: Literal["informativo", "atenção", "alto"]
    mensagem: str


class Panorama(BaseModel):
    resumo: str = Field(description="Panorama do momento em 3 a 6 frases: juros, inflação, câmbio, política, exterior")
    temas: list[str] = Field(description="3 a 6 temas que dominam o mercado agora")
    setores_favorecidos: list[str]
    setores_pressionados: list[str]
    alertas_carteira: list[AlertaCarteira]
    sugestoes_diversificacao: list[str] = Field(description="2 a 4 observações sobre concentração por setor, moeda ou tipo na carteira e nas candidatas")


# ---------------------------------------------------------------------------
# Seleção do universo e montagem do contexto
# ---------------------------------------------------------------------------
def selecionar_universo(ranking: pd.DataFrame, carteira: pd.DataFrame, maximo: int = MAXIMO_PADRAO) -> pd.DataFrame:
    """Consenso (aprovados em 2+ métodos ou top 20 em 2+ métodos) + papéis da carteira, até `maximo`."""
    base = ranking.copy()
    top = estrategias.consenso_top_n(base, top_n=20, minimo_modelos=2)
    aprovados = base[base["qtd_estrategias_aprovado"] >= 2]
    candidatos = pd.concat([aprovados, top], ignore_index=True).drop_duplicates("ticker")
    candidatos = candidatos.sort_values("pontuacao_geral", ascending=False).head(maximo)
    na_carteira = base[base["ticker"].isin(set(carteira["ticker"]))]
    universo = pd.concat([candidatos, na_carteira], ignore_index=True).drop_duplicates("ticker")
    universo["na_carteira"] = universo["ticker"].isin(set(carteira["ticker"]))
    return universo.reset_index(drop=True)


def _num(v, casas=2):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return round(float(v), casas)


def descrever_papel(linha: pd.Series, manchetes: list[dict]) -> dict:
    """Resumo compacto de um papel para o prompt (só o que o modelo precisa)."""
    return {
        "ticker": linha["ticker"], "empresa": linha.get("nome"), "pais": linha["pais"], "setor": linha.get("setor"),
        "na_carteira": bool(linha.get("na_carteira", False)),
        "preco": _num(linha["preco"]), "pl": _num(linha["pl"]), "pvp": _num(linha["pvp"]), "dy_pct": _num(linha["dy"] * 100, 1),
        "ev_ebit": _num(linha["ev_ebit"]), "roic_pct": _num(linha["roic"] * 100, 1), "roe_pct": _num(linha["roe"] * 100, 1),
        "margem_liquida_pct": _num(linha["margem_liquida"] * 100, 1), "margem_bruta_pct": _num(linha.get("margem_bruta", math.nan) * 100, 1),
        "divida_liquida_sobre_pl": _num(linha["divida_patrimonio"]), "liquidez_corrente": _num(linha["liquidez_corrente"]),
        "crescimento_receita_pct": _num(linha["cresc_receita_5a"] * 100, 1), "earnings_yield_pct": _num(linha.get("earnings_yield", math.nan) * 100, 1),
        "preco_justo_graham": _num(linha.get("preco_justo_graham")), "preco_teto_bazin": _num(linha.get("preco_teto_bazin")),
        "aprovado_em": linha.get("estrategias_aprovado") if isinstance(linha.get("estrategias_aprovado"), str) else "",
        "posicoes": {"magica": _num(linha.get("posicao_magica"), 0), "graham": _num(linha.get("posicao_graham"), 0), "dividendos": _num(linha.get("posicao_dividendos"), 0), "buffett": _num(linha.get("posicao_buffett"), 0)},
        "manchetes": [{"data": m.get("data"), "fonte": m.get("fonte"), "titulo": m.get("titulo")} for m in manchetes],
    }


def descrever_macro(macro: dict) -> dict:
    chaves = ("ipca_12m", "ipca_esperado_12m", "selic_meta", "cdi_12m", "juro_real_selic", "dolar", "igpm_12m", "meta_inflacao")
    return {k: _num(macro.get(k), 4) for k in chaves}


SISTEMA = """Você é um analista de investimentos experiente, no estilo de Benjamin Graham, Warren Buffett, Joel Greenblatt e Décio Bazin: cético, focado em médio e longo prazo (3 a 10 anos), avesso a modismos e a previsões de curto prazo.

Você recebe ações que um screener quantitativo apontou como baratas, com fundamentos, posição em cada método, cenário macro e manchetes recentes. Seu trabalho é o que os números não fazem: explicar POR QUE cada ação está barata, separar oportunidade de armadilha de valor, apontar riscos concretos e dizer a que cenários o negócio é sensível.

Regras:
- Não preveja preços nem direção do mercado. Raciocine sobre negócio, balanço, setor e cenários.
- Seja específico e direto. Evite frases genéricas que serviriam para qualquer empresa.
- Use o conhecimento que tem sobre cada empresa e setor; se não conhecer bem a empresa, diga isso na tese e reduza a convicção.
- "armadilha provável" é para lucro não recorrente, setor em declínio estrutural, governança ruim ou dívida perigosa. "oportunidade" exige negócio sólido + preço baixo por motivo temporário. O resto é "estudar".
- Considere que o investidor é brasileiro, busca ganhar da inflação (IPCA) e da Selic no longo prazo e quer diversificar entre tipos de ativo e moedas (BRL e USD).
- Responda em português do Brasil."""


def _cliente():
    import anthropic

    return anthropic.Anthropic()


def analisar_lote(cliente, papeis: list[dict], macro: dict, data: str) -> list[AnalisePapel]:
    conteudo = (
        f"Data: {data}\nCenário macro (frações; ex.: 0.1375 = 13,75%): {json.dumps(macro, ensure_ascii=False)}\n\n"
        f"Analise cada um destes {len(papeis)} papéis e devolva um item por ticker, na mesma ordem:\n"
        f"{json.dumps(papeis, ensure_ascii=False)}"
    )
    resposta = cliente.messages.parse(
        model=MODELO,
        max_tokens=16000,
        system=SISTEMA,
        output_config={"effort": "high"},
        messages=[{"role": "user", "content": conteudo}],
        output_format=LoteAnalise,
    )
    if resposta.stop_reason == "refusal":
        raise RuntimeError(f"Modelo recusou a análise: {getattr(resposta.stop_details, 'explanation', '')}")
    lote: LoteAnalise = resposta.parsed_output
    return lote.papeis


def analisar_panorama(cliente, macro: dict, noticias_mercado: dict[str, list[dict]], resumo_universo: list[dict], carteira_resumo: list[dict], data: str) -> Panorama:
    conteudo = (
        f"Data: {data}\nCenário macro: {json.dumps(macro, ensure_ascii=False)}\n\n"
        f"Manchetes de mercado da semana:\n{json.dumps(noticias_mercado, ensure_ascii=False)}\n\n"
        f"Carteira atual do investidor (tipo, moeda, setor quando conhecido):\n{json.dumps(carteira_resumo, ensure_ascii=False)}\n\n"
        f"Candidatas do screener hoje (ticker, setor, país, classificação dada por você):\n{json.dumps(resumo_universo, ensure_ascii=False)}\n\n"
        "Escreva o panorama do momento, os temas dominantes, setores favorecidos e pressionados neste cenário, alertas sobre posições da carteira "
        "(só quando houver motivo concreto nas manchetes ou nos fundamentos) e observações de diversificação."
    )
    resposta = cliente.messages.parse(
        model=MODELO,
        max_tokens=16000,
        system=SISTEMA,
        output_config={"effort": "high"},
        messages=[{"role": "user", "content": conteudo}],
        output_format=Panorama,
    )
    if resposta.stop_reason == "refusal":
        raise RuntimeError("Modelo recusou o panorama")
    return resposta.parsed_output


def executar(maximo: int = MAXIMO_PADRAO, cliente=None, buscar_noticias: bool = True) -> dict | None:
    if cliente is None and not os.environ.get("ANTHROPIC_API_KEY"):
        log.warning("ANTHROPIC_API_KEY não definida: análise por IA pulada.")
        return None
    cliente = cliente or _cliente()
    inicio = datetime.now()
    data = inicio.strftime("%Y-%m-%d")

    ranking = pd.read_csv(config.PASTA_DADOS / "ranking.csv")
    macro = json.loads((config.PASTA_DADOS / "macro.json").read_text(encoding="utf-8")) if (config.PASTA_DADOS / "macro.json").exists() else {}
    carteira = carregar_carteira()
    universo = selecionar_universo(ranking, carteira, maximo=maximo)
    log.info("Universo da análise: %d papéis (%d da carteira).", len(universo), int(universo["na_carteira"].sum()))

    manchetes: dict[str, list[dict]] = {}
    mercado: dict[str, list[dict]] = {}
    if buscar_noticias:
        manchetes = noticias.noticias_por_empresa([(r["ticker"], r.get("nome"), r["pais"]) for _, r in universo.iterrows()])
        mercado = noticias.noticias_de_mercado()

    macro_desc = descrever_macro(macro)
    analises: list[AnalisePapel] = []
    papeis = [descrever_papel(linha, manchetes.get(linha["ticker"], [])) for _, linha in universo.iterrows()]
    for i in range(0, len(papeis), PAPEIS_POR_CHAMADA):
        lote = papeis[i:i + PAPEIS_POR_CHAMADA]
        try:
            analises.extend(analisar_lote(cliente, lote, macro_desc, data))
        except Exception as erro:  # noqa: BLE001
            log.exception("Falha no lote %d: %s", i // PAPEIS_POR_CHAMADA + 1, erro)

    por_ticker = {a.ticker: a for a in analises}
    resumo_universo = [{"ticker": p["ticker"], "setor": p["setor"], "pais": p["pais"], "classificacao": por_ticker[p["ticker"]].classificacao if p["ticker"] in por_ticker else None} for p in papeis]
    setores = dict(zip(ranking["ticker"], ranking.get("setor", pd.Series(dtype=object))))
    carteira_resumo = [{"ticker": r["ticker"] or r.get("descricao"), "tipo": r["tipo"], "moeda": r["moeda"], "setor": setores.get(r["ticker"])} for _, r in carteira.iterrows()]
    panorama = None
    try:
        panorama = analisar_panorama(cliente, macro_desc, mercado, resumo_universo, carteira_resumo, data)
    except Exception as erro:  # noqa: BLE001
        log.exception("Falha no panorama: %s", erro)

    saida = {
        "data": data,
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "modelo": MODELO,
        "aviso": AVISO,
        "duracao_segundos": round((datetime.now() - inicio).total_seconds(), 1),
        "panorama": panorama.model_dump() if panorama else None,
        "papeis": [
            {**a.model_dump(), "pais": p["pais"], "setor": p["setor"], "empresa": p["empresa"], "preco": p["preco"], "na_carteira": p["na_carteira"],
             "aprovado_em": p["aprovado_em"], "posicoes": p["posicoes"], "manchetes": manchetes.get(a.ticker, [])}
            for p in papeis for a in [por_ticker.get(p["ticker"])] if a is not None
        ],
        "sem_analise": [p["ticker"] for p in papeis if p["ticker"] not in por_ticker],
    }
    config.PASTA_DADOS.mkdir(parents=True, exist_ok=True)
    ARQ_ANALISE.write_text(json.dumps(saida, ensure_ascii=False, indent=2), encoding="utf-8")
    config.PASTA_HISTORICO.mkdir(parents=True, exist_ok=True)
    (config.PASTA_HISTORICO / f"analise_ia_{data}.json").write_text(json.dumps(saida, ensure_ascii=False), encoding="utf-8")
    log.info("Análise por IA concluída: %d papéis em %.0fs.", len(saida["papeis"]), saida["duracao_segundos"])
    return saida


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Análise qualitativa diária com o Claude.")
    parser.add_argument("--maximo", type=int, default=MAXIMO_PADRAO, help="máximo de papéis do screener a analisar (além da carteira)")
    parser.add_argument("--sem-noticias", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    executar(maximo=args.maximo, buscar_noticias=not args.sem_noticias)
    return 0


if __name__ == "__main__":
    sys.exit(main())

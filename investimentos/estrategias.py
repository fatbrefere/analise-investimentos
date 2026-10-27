"""
Estratégias de seleção de ações.

Cada função recebe um DataFrame no esquema comum (ver fontes/comum.py) e
devolve o mesmo DataFrame com colunas de pontuação/aprovação, ordenado do
melhor para o pior. Todas aceitam os parâmetros como argumentos para a
tela do Streamlit poder ajustá-los em tempo real.

Resumo dos métodos:
- Fórmula Mágica (Greenblatt): ranking por EV/EBIT baixo + ROIC alto.
- Graham: ações baratas em relação a lucro e patrimônio, com balanço sólido;
  preço justo = raiz(22,5 x LPA x VPA).
- Dividendos (Bazin/Barsi): DY >= 6%, preço teto = DPA / 6%, dívida sob
  controle, preferência por setores perenes.
- Buffett: empresa de qualidade (ROE, margem, pouca dívida, crescimento)
  a preço razoável.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from investimentos import config

NOMES_ESTRATEGIAS = {
    "magica": "Fórmula Mágica (Greenblatt)",
    "graham": "Valor (Graham)",
    "dividendos": "Dividendos (Bazin / Barsi)",
    "buffett": "Qualidade (Buffett)",
}


def filtrar_liquidez(df: pd.DataFrame, liquidez_minima_br: float = config.LIQUIDEZ_MINIMA_BR, volume_minimo_us: float = config.VOLUME_MINIMO_US) -> pd.DataFrame:
    """Remove papéis sem liquidez e sem preço."""
    df = df[df["preco"].notna() & (df["preco"] > 0)].copy()
    minimo = np.where(df["pais"] == "US", volume_minimo_us, liquidez_minima_br)
    return df[df["liquidez"].fillna(0) >= minimo].copy()


def _rank(serie: pd.Series, crescente: bool) -> pd.Series:
    return serie.rank(ascending=crescente, method="min", na_option="bottom")


# ---------------------------------------------------------------------------
# Fórmula Mágica
# ---------------------------------------------------------------------------
def formula_magica(df: pd.DataFrame, top_n: int = config.MAGICA_TOP_N, ev_ebit_minimo: float = config.MAGICA_EV_EBIT_MINIMO, roic_minimo: float = config.MAGICA_ROIC_MINIMO) -> pd.DataFrame:
    base = df[(df["ev_ebit"] > ev_ebit_minimo) & (df["roic"] > roic_minimo)].copy()
    if base.empty:
        base["rank_ev_ebit"] = base["rank_roic"] = base["pontos_magica"] = base["posicao_magica"] = pd.Series(dtype=float)
        base["aprovado_magica"] = pd.Series(dtype=bool)
        return base
    base["rank_ev_ebit"] = _rank(base["ev_ebit"], crescente=True)
    base["rank_roic"] = _rank(base["roic"], crescente=False)
    base["pontos_magica"] = base["rank_ev_ebit"] + base["rank_roic"]
    base = base.sort_values(["pontos_magica", "ev_ebit"]).reset_index(drop=True)
    base["posicao_magica"] = np.arange(1, len(base) + 1)
    base["aprovado_magica"] = base["posicao_magica"] <= top_n
    return base


# ---------------------------------------------------------------------------
# Graham
# ---------------------------------------------------------------------------
def preco_justo_graham(lpa: float, vpa: float, multiplicador: float = config.GRAHAM_PL_X_PVP_MAXIMO) -> float:
    """Número de Graham: raiz(22,5 x LPA x VPA). Só existe para lucro e patrimônio positivos."""
    if lpa is None or vpa is None or math.isnan(lpa) or math.isnan(vpa) or lpa <= 0 or vpa <= 0:
        return math.nan
    return math.sqrt(multiplicador * lpa * vpa)


def graham(df: pd.DataFrame, pl_maximo: float = config.GRAHAM_PL_MAXIMO, pvp_maximo: float = config.GRAHAM_PVP_MAXIMO, pl_x_pvp_maximo: float = config.GRAHAM_PL_X_PVP_MAXIMO, liquidez_corrente_minima: float = config.GRAHAM_LIQUIDEZ_CORRENTE_MINIMA, divida_patrimonio_maxima: float = config.GRAHAM_DIVIDA_PATRIMONIO_MAXIMA, margem_seguranca_minima: float = config.GRAHAM_MARGEM_SEGURANCA_MINIMA) -> pd.DataFrame:
    base = df.copy()
    base["preco_justo_graham"] = [preco_justo_graham(l, v, pl_x_pvp_maximo) for l, v in zip(base["lpa"], base["vpa"])]
    base["margem_seguranca_graham"] = base["preco_justo_graham"] / base["preco"] - 1
    base["pl_x_pvp"] = base["pl"] * base["pvp"]

    criterios = {
        "g_lucro_positivo": base["pl"] > 0,
        "g_pl": (base["pl"] > 0) & (base["pl"] <= pl_maximo),
        "g_pvp": (base["pvp"] > 0) & (base["pvp"] <= pvp_maximo),
        "g_pl_x_pvp": (base["pl_x_pvp"] > 0) & (base["pl_x_pvp"] <= pl_x_pvp_maximo),
        "g_liquidez_corrente": base["liquidez_corrente"].isna() | (base["liquidez_corrente"] >= liquidez_corrente_minima),
        "g_divida": base["divida_patrimonio"].isna() | (base["divida_patrimonio"] <= divida_patrimonio_maxima),
        "g_margem_seguranca": base["margem_seguranca_graham"] >= margem_seguranca_minima,
    }
    for nome, serie in criterios.items():
        base[nome] = serie.fillna(False).astype(bool)
    base["pontos_graham"] = base[list(criterios)].sum(axis=1)
    base["aprovado_graham"] = base["pontos_graham"] == len(criterios)
    return base.sort_values(["pontos_graham", "margem_seguranca_graham"], ascending=[False, False]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Dividendos (Bazin / Barsi)
# ---------------------------------------------------------------------------
def preco_teto_bazin(dpa: float, dy_minimo: float = config.BAZIN_DY_MINIMO) -> float:
    if dpa is None or math.isnan(dpa) or dpa <= 0 or dy_minimo <= 0:
        return math.nan
    return dpa / dy_minimo


def dividendos(df: pd.DataFrame, dy_minimo: float = config.BAZIN_DY_MINIMO, divida_patrimonio_maxima: float = config.BAZIN_DIVIDA_PATRIMONIO_MAXIMA, desconto_minimo: float = config.BAZIN_DESCONTO_MINIMO_PRECO_TETO) -> pd.DataFrame:
    base = df.copy()
    base["preco_teto_bazin"] = [preco_teto_bazin(d, dy_minimo) for d in base["dpa"]]
    base["desconto_preco_teto"] = 1 - base["preco"] / base["preco_teto_bazin"]
    if "setor_barsi" not in base.columns:
        base["setor_barsi"] = None

    criterios = {
        "d_dy": base["dy"] >= dy_minimo,
        "d_preco_teto": base["desconto_preco_teto"] >= desconto_minimo,
        "d_lucro_positivo": base["pl"] > 0,
        "d_divida": base["divida_patrimonio"].isna() | (base["divida_patrimonio"] <= divida_patrimonio_maxima),
    }
    for nome, serie in criterios.items():
        base[nome] = serie.fillna(False).astype(bool)
    base["d_setor_perene"] = base["setor_barsi"].notna()
    base["pontos_dividendos"] = base[list(criterios)].sum(axis=1) + base["d_setor_perene"].astype(int) * 0.5
    base["aprovado_dividendos"] = base[list(criterios)].all(axis=1)
    return base.sort_values(["pontos_dividendos", "dy"], ascending=[False, False]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Buffett (qualidade a preço razoável)
# ---------------------------------------------------------------------------
def buffett(df: pd.DataFrame, roe_minimo: float = config.BUFFETT_ROE_MINIMO, margem_liquida_minima: float = config.BUFFETT_MARGEM_LIQUIDA_MINIMA, divida_patrimonio_maxima: float = config.BUFFETT_DIVIDA_PATRIMONIO_MAXIMA, crescimento_minimo: float = config.BUFFETT_CRESCIMENTO_RECEITA_MINIMO, pl_maximo: float = config.BUFFETT_PL_MAXIMO, pvp_maximo: float = config.BUFFETT_PVP_MAXIMO) -> pd.DataFrame:
    base = df.copy()
    criterios = {
        "b_roe": base["roe"] >= roe_minimo,
        "b_margem": base["margem_liquida"] >= margem_liquida_minima,
        "b_divida": base["divida_patrimonio"].isna() | (base["divida_patrimonio"] <= divida_patrimonio_maxima),
        "b_crescimento": base["cresc_receita_5a"].isna() | (base["cresc_receita_5a"] > crescimento_minimo),
        "b_pl": (base["pl"] > 0) & (base["pl"] <= pl_maximo),
        "b_pvp": (base["pvp"] > 0) & (base["pvp"] <= pvp_maximo),
    }
    for nome, serie in criterios.items():
        base[nome] = serie.fillna(False).astype(bool)
    base["pontos_buffett"] = base[list(criterios)].sum(axis=1)
    base["aprovado_buffett"] = base["pontos_buffett"] == len(criterios)
    # desempate: ROE mais alto e P/L mais baixo
    base["rank_qualidade"] = _rank(base["roe"], crescente=False) + _rank(base["pl"].where(base["pl"] > 0), crescente=True)
    return base.sort_values(["pontos_buffett", "rank_qualidade"], ascending=[False, True]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Inflação: a ação precisa render mais que o IPCA + prêmio
# ---------------------------------------------------------------------------
def taxa_minima_atratividade(ipca_12m: float, premio: float = config.PREMIO_DE_RISCO_SOBRE_IPCA, selic: float = math.nan) -> float:
    """Maior entre (IPCA + prêmio) e a Selic: não faz sentido correr risco para render menos que o título público."""
    candidatos = [v for v in (ipca_12m + premio if not math.isnan(ipca_12m) else math.nan, selic) if not math.isnan(v)]
    return max(candidatos) if candidatos else math.nan


def adicionar_earnings_yield(df: pd.DataFrame, taxa_minima: float) -> pd.DataFrame:
    """Earnings yield = LPA / preço = 1 / P/L. Compara com a taxa mínima de atratividade."""
    base = df.copy()
    base["earnings_yield"] = np.where(base["pl"] > 0, 1 / base["pl"], np.nan)
    base["bate_inflacao"] = (base["earnings_yield"] >= taxa_minima) if not math.isnan(taxa_minima) else pd.NA
    return base


# ---------------------------------------------------------------------------
# Consolidação
# ---------------------------------------------------------------------------
def consolidar(df: pd.DataFrame, taxa_minima: float = math.nan, parametros: dict | None = None) -> pd.DataFrame:
    """Roda todas as estratégias e junta os resultados em uma tabela só.

    `parametros` permite sobrescrever os limites de cada estratégia:
    {"magica": {...}, "graham": {...}, "dividendos": {...}, "buffett": {...}}
    """
    parametros = parametros or {}
    base = df.copy().reset_index(drop=True)
    if base.empty:
        return base

    m = formula_magica(base, **parametros.get("magica", {}))
    g = graham(base, **parametros.get("graham", {}))
    d = dividendos(base, **parametros.get("dividendos", {}))
    b = buffett(base, **parametros.get("buffett", {}))

    cols_m = ["ticker", "rank_ev_ebit", "rank_roic", "pontos_magica", "posicao_magica", "aprovado_magica"]
    cols_g = ["ticker", "preco_justo_graham", "margem_seguranca_graham", "pl_x_pvp", "pontos_graham", "aprovado_graham"] + [c for c in g.columns if c.startswith("g_")]
    cols_d = ["ticker", "preco_teto_bazin", "desconto_preco_teto", "pontos_dividendos", "aprovado_dividendos"] + [c for c in d.columns if c.startswith("d_")]
    cols_b = ["ticker", "pontos_buffett", "aprovado_buffett", "rank_qualidade"] + [c for c in b.columns if c.startswith("b_")]

    resultado = base.merge(m[cols_m], on="ticker", how="left")
    resultado = resultado.merge(g[cols_g], on="ticker", how="left")
    resultado = resultado.merge(d[cols_d], on="ticker", how="left")
    resultado = resultado.merge(b[cols_b], on="ticker", how="left")

    for coluna in ("aprovado_magica", "aprovado_graham", "aprovado_dividendos", "aprovado_buffett"):
        resultado[coluna] = resultado[coluna].fillna(False).astype(bool)

    resultado = adicionar_earnings_yield(resultado, taxa_minima)
    resultado["qtd_estrategias_aprovado"] = resultado[["aprovado_magica", "aprovado_graham", "aprovado_dividendos", "aprovado_buffett"]].sum(axis=1)
    resultado["estrategias_aprovado"] = resultado.apply(
        lambda linha: ", ".join(
            nome for chave, nome in (("magica", "Mágica"), ("graham", "Graham"), ("dividendos", "Dividendos"), ("buffett", "Buffett"))
            if linha[f"aprovado_{chave}"]
        ),
        axis=1,
    )
    # Pontuação geral: estratégias aprovadas pesam mais; os pontos parciais desempatam
    resultado["pontuacao_geral"] = (
        resultado["qtd_estrategias_aprovado"] * 10
        + resultado["pontos_graham"].fillna(0)
        + resultado["pontos_dividendos"].fillna(0)
        + resultado["pontos_buffett"].fillna(0)
        + np.where(resultado["posicao_magica"].notna(), np.clip(7 - resultado["posicao_magica"].fillna(999) / 10, 0, 7), 0)
    )
    return resultado.sort_values(["pontuacao_geral", "qtd_estrategias_aprovado"], ascending=False).reset_index(drop=True)

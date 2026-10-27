"""
Esquema comum de dados fundamentalistas.

Todas as fontes (Fundamentus para B3, Yahoo Finance para EUA) são
normalizadas para as mesmas colunas, com percentuais em fração decimal
(ex.: 12,5% -> 0.125). Assim as estratégias funcionam igual para qualquer
mercado.
"""
from __future__ import annotations

import math
import re

import pandas as pd

COLUNAS_FUNDAMENTOS = [
    "ticker",            # código do papel (PETR4, AAPL)
    "nome",              # nome da empresa (quando disponível)
    "pais",              # "BR" ou "US"
    "moeda",             # "BRL" ou "USD"
    "setor",             # setor (quando disponível)
    "preco",             # cotação atual
    "pl",                # Preço / Lucro
    "pvp",               # Preço / Valor Patrimonial
    "dy",                # Dividend yield 12 meses (fração)
    "ev_ebit",           # Enterprise Value / EBIT
    "ev_ebitda",         # Enterprise Value / EBITDA
    "roic",              # Retorno sobre capital investido (fração)
    "roe",               # Retorno sobre patrimônio (fração)
    "margem_ebit",       # Margem EBIT (fração)
    "margem_liquida",    # Margem líquida (fração)
    "liquidez_corrente", # Ativo circulante / Passivo circulante
    "divida_patrimonio", # Dívida bruta / Patrimônio líquido
    "cresc_receita_5a",  # Crescimento da receita em 5 anos (fração)
    "liquidez",          # Liquidez de negociação (R$ em 2 meses ou US$ volume médio diário)
    "patrimonio_liquido",
    "lpa",               # Lucro por ação
    "vpa",               # Valor patrimonial por ação
    "dpa",               # Dividendo por ação (12 meses)
]


def numero_br(valor) -> float:
    """Converte textos no formato brasileiro ('1.234,56', '12,3%') para float.

    Percentuais viram fração decimal (12,3% -> 0.123). Valores vazios,
    '-' ou inválidos viram NaN.
    """
    if valor is None:
        return math.nan
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip()
    if texto in ("", "-", "nan", "NaN", "None"):
        return math.nan
    percentual = texto.endswith("%")
    texto = texto.replace("%", "").replace(".", "").replace(",", ".")
    texto = re.sub(r"[^0-9eE+\-.]", "", texto)
    if texto in ("", "-", ".", "-."):
        return math.nan
    try:
        numero = float(texto)
    except ValueError:
        return math.nan
    return numero / 100.0 if percentual else numero


def completar_colunas(df: pd.DataFrame) -> pd.DataFrame:
    """Garante que o DataFrame tenha todas as colunas do esquema, na ordem padrão."""
    for coluna in COLUNAS_FUNDAMENTOS:
        if coluna not in df.columns:
            df[coluna] = pd.NA
    df = df[COLUNAS_FUNDAMENTOS].copy()
    numericas = [c for c in COLUNAS_FUNDAMENTOS if c not in ("ticker", "nome", "pais", "moeda", "setor")]
    for coluna in numericas:
        df[coluna] = pd.to_numeric(df[coluna], errors="coerce")
    return df


def derivar_por_acao(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula LPA, VPA e DPA a partir de preço, P/L, P/VP e DY quando faltarem."""
    df = df.copy()
    with pd.option_context("mode.chained_assignment", None):
        if "lpa" not in df or df["lpa"].isna().all():
            df["lpa"] = df["preco"] / df["pl"]
        if "vpa" not in df or df["vpa"].isna().all():
            df["vpa"] = df["preco"] / df["pvp"]
        if "dpa" not in df or df["dpa"].isna().all():
            df["dpa"] = df["preco"] * df["dy"]
    # P/L negativo gera LPA negativo (prejuízo), o que é informação útil.
    # P/L ou P/VP zero (divisão por zero) viram NaN.
    for coluna in ("lpa", "vpa", "dpa"):
        df[coluna] = df[coluna].replace([float("inf"), float("-inf")], pd.NA)
        df[coluna] = pd.to_numeric(df[coluna], errors="coerce")
    return df

"""
Indicadores macroeconômicos do Banco Central do Brasil (API SGS).

Documentação: https://dadosabertos.bcb.gov.br/dataset/
Exemplo: https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados/ultimos/12?formato=json
"""
from __future__ import annotations

import logging
import math
from datetime import date

import pandas as pd
import requests

from investimentos import config

log = logging.getLogger(__name__)

URL_SGS = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados/ultimos/{n}?formato=json"


def obter_serie(codigo: int, ultimos: int) -> pd.DataFrame:
    """Retorna DataFrame com colunas data (datetime) e valor (float)."""
    url = URL_SGS.format(codigo=codigo, n=ultimos)
    resposta = requests.get(url, headers=config.HTTP_HEADERS, timeout=config.HTTP_TIMEOUT)
    resposta.raise_for_status()
    return serie_para_dataframe(resposta.json())


def serie_para_dataframe(registros: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(registros)
    if df.empty:
        return pd.DataFrame(columns=["data", "valor"])
    df["data"] = pd.to_datetime(df["data"], format="%d/%m/%Y")
    df["valor"] = pd.to_numeric(df["valor"].astype(str).str.replace(",", "."), errors="coerce")
    return df.dropna().sort_values("data").reset_index(drop=True)


def acumular(df: pd.DataFrame, ultimos: int | None = None) -> float:
    """Acumula variações percentuais mensais/diárias: prod(1 + v/100) - 1."""
    if df.empty:
        return math.nan
    valores = df["valor"].tail(ultimos) if ultimos else df["valor"]
    return float((1 + valores / 100.0).prod() - 1)


def obter_macro() -> dict:
    """Coleta IPCA 12m, Selic, CDI 12m e dólar. Cada item falha de forma independente."""
    macro = {
        "data_referencia": date.today().isoformat(),
        "ipca_12m": math.nan,
        "ipca_ultimo_mes": math.nan,
        "ipca_mes_referencia": None,
        "selic_meta": math.nan,
        "cdi_12m": math.nan,
        "dolar": math.nan,
        "fonte_dolar": None,
    }
    try:
        ipca = obter_serie(config.SERIES_BCB["ipca_mensal"], 12)
        macro["ipca_12m"] = acumular(ipca)
        macro["ipca_ultimo_mes"] = float(ipca["valor"].iloc[-1]) / 100.0
        macro["ipca_mes_referencia"] = ipca["data"].iloc[-1].strftime("%m/%Y")
    except Exception as erro:  # noqa: BLE001
        log.warning("Falha ao obter IPCA no BCB: %s", erro)
    try:
        selic = obter_serie(config.SERIES_BCB["selic_meta"], 1)
        macro["selic_meta"] = float(selic["valor"].iloc[-1]) / 100.0
    except Exception as erro:  # noqa: BLE001
        log.warning("Falha ao obter Selic no BCB: %s", erro)
    try:
        cdi = obter_serie(config.SERIES_BCB["cdi_diario"], 252)
        macro["cdi_12m"] = acumular(cdi)
    except Exception as erro:  # noqa: BLE001
        log.warning("Falha ao obter CDI no BCB: %s", erro)
    try:
        dolar = obter_serie(config.SERIES_BCB["dolar_ptax"], 1)
        macro["dolar"] = float(dolar["valor"].iloc[-1])
        macro["fonte_dolar"] = "BCB PTAX"
    except Exception as erro:  # noqa: BLE001
        log.warning("Falha ao obter dólar no BCB: %s", erro)
    return macro

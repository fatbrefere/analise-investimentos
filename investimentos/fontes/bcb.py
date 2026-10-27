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
        "fonte_cdi": None,
        "erros": {},
    }
    try:
        ipca = obter_serie(config.SERIES_BCB["ipca_mensal"], 12)
        macro["ipca_12m"] = acumular(ipca)
        macro["ipca_ultimo_mes"] = float(ipca["valor"].iloc[-1]) / 100.0
        macro["ipca_mes_referencia"] = ipca["data"].iloc[-1].strftime("%m/%Y")
    except Exception as erro:  # noqa: BLE001
        log.warning("Falha ao obter IPCA no BCB: %s", erro)
        macro["erros"]["ipca"] = f"{type(erro).__name__}: {erro}"
    try:
        selic = obter_serie(config.SERIES_BCB["selic_meta"], 1)
        macro["selic_meta"] = float(selic["valor"].iloc[-1]) / 100.0
    except Exception as erro:  # noqa: BLE001
        log.warning("Falha ao obter Selic no BCB: %s", erro)
        macro["erros"]["selic"] = f"{type(erro).__name__}: {erro}"
    try:
        cdi = obter_serie(config.SERIES_BCB["cdi_diario"], 252)
        if cdi.empty:
            raise ValueError("série vazia")
        macro["cdi_12m"] = acumular(cdi)
        macro["fonte_cdi"] = "BCB 12 (acumulado 252 dias úteis)"
    except Exception as erro:  # noqa: BLE001
        log.warning("Falha ao obter CDI diário no BCB (%s); tentando CDI anualizado.", erro)
        macro["erros"]["cdi_diario"] = f"{type(erro).__name__}: {erro}"
        try:
            cdi_aa = obter_serie(config.SERIES_BCB["cdi_anual"], 1)
            macro["cdi_12m"] = float(cdi_aa["valor"].iloc[-1]) / 100.0
            macro["fonte_cdi"] = "BCB 4389 (taxa anualizada atual)"
        except Exception as erro2:  # noqa: BLE001
            log.warning("Falha ao obter CDI anualizado no BCB: %s", erro2)
            macro["erros"]["cdi_anual"] = f"{type(erro2).__name__}: {erro2}"
    try:
        dolar = obter_serie(config.SERIES_BCB["dolar_ptax"], 1)
        macro["dolar"] = float(dolar["valor"].iloc[-1])
        macro["fonte_dolar"] = "BCB PTAX"
    except Exception as erro:  # noqa: BLE001
        log.warning("Falha ao obter dólar no BCB: %s", erro)
        macro["erros"]["dolar"] = f"{type(erro).__name__}: {erro}"
    return macro

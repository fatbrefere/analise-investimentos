"""
Indicadores macroeconômicos do Banco Central do Brasil (API SGS).

Documentação: https://dadosabertos.bcb.gov.br/dataset/
Exemplo: https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados/ultimos/12?formato=json
"""
from __future__ import annotations

import logging
import math
import time
from datetime import date, timedelta

import pandas as pd
import requests

from investimentos import config

log = logging.getLogger(__name__)

URL_SGS = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados/ultimos/{n}?formato=json"
URL_SGS_PERIODO = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json&dataInicial={inicio}&dataFinal={fim}"


def _get_json(url: str, tentativas: int = 3):
    """GET com repetição: a API do BCB costuma dar timeout ou 502 de forma passageira."""
    ultimo_erro: Exception | None = None
    for tentativa in range(tentativas):
        try:
            resposta = requests.get(url, headers=config.HTTP_HEADERS, timeout=config.HTTP_TIMEOUT)
            if resposta.status_code >= 500:
                resposta.raise_for_status()
            resposta.raise_for_status()
            return resposta.json()
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as erro:
            if isinstance(erro, requests.HTTPError) and erro.response is not None and erro.response.status_code < 500:
                raise  # erro de cliente (400, 404): repetir não ajuda
            ultimo_erro = erro
            log.warning("BCB tentativa %d/%d falhou (%s); aguardando.", tentativa + 1, tentativas, erro)
            time.sleep(2 * (tentativa + 1))
    raise ultimo_erro  # type: ignore[misc]


def obter_serie(codigo: int, ultimos: int) -> pd.DataFrame:
    """Retorna DataFrame com colunas data (datetime) e valor (float)."""
    return serie_para_dataframe(_get_json(URL_SGS.format(codigo=codigo, n=ultimos)))


def obter_serie_periodo(codigo: int, dias: int) -> pd.DataFrame:
    """Série por intervalo de datas (a forma documentada da API; 'ultimos/N' falha para séries diárias longas)."""
    fim = date.today()
    inicio = fim - timedelta(days=dias)
    url = URL_SGS_PERIODO.format(codigo=codigo, inicio=inicio.strftime("%d/%m/%Y"), fim=fim.strftime("%d/%m/%Y"))
    return serie_para_dataframe(_get_json(url))


def serie_para_dataframe(registros: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(registros)
    if df.empty:
        return pd.DataFrame(columns=["data", "valor"])
    df["data"] = pd.to_datetime(df["data"], format="%d/%m/%Y")
    df["valor"] = pd.to_numeric(df["valor"].astype(str).str.replace(",", "."), errors="coerce")
    return df.dropna().sort_values("data").reset_index(drop=True)


def obter_focus_ipca_12m() -> float:
    """Mediana das expectativas do boletim Focus para o IPCA nos próximos 12 meses (fração)."""
    return focus_para_fracao(_get_json(config.URL_FOCUS_IPCA_12M))


def focus_para_fracao(payload: dict) -> float:
    valores = payload.get("value") or []
    if not valores:
        raise ValueError("resposta do Focus sem valores")
    return float(valores[0]["Mediana"]) / 100.0


def juro_real(taxa_nominal: float, inflacao: float) -> float:
    """Equação de Fisher: (1 + nominal) / (1 + inflação) - 1."""
    if taxa_nominal is None or inflacao is None or math.isnan(taxa_nominal) or math.isnan(inflacao):
        return math.nan
    return (1 + taxa_nominal) / (1 + inflacao) - 1


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
        "ipca_no_ano": math.nan,
        "igpm_12m": math.nan,
        "ipca_esperado_12m": math.nan,
        "juro_real_selic": math.nan,
        "juro_real_cdi": math.nan,
        "meta_inflacao": config.META_INFLACAO,
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
        ano_atual = ipca["data"].iloc[-1].year
        macro["ipca_no_ano"] = acumular(ipca[ipca["data"].dt.year == ano_atual])
    except Exception as erro:  # noqa: BLE001
        log.warning("Falha ao obter IPCA no BCB: %s", erro)
        macro["erros"]["ipca"] = f"{type(erro).__name__}: {erro}"
    try:
        igpm = obter_serie(config.SERIES_BCB["igpm_mensal"], 12)
        macro["igpm_12m"] = acumular(igpm)
    except Exception as erro:  # noqa: BLE001
        log.warning("Falha ao obter IGP-M no BCB: %s", erro)
        macro["erros"]["igpm"] = f"{type(erro).__name__}: {erro}"
    try:
        macro["ipca_esperado_12m"] = obter_focus_ipca_12m()
    except Exception as erro:  # noqa: BLE001
        log.warning("Falha ao obter expectativa Focus: %s", erro)
        macro["erros"]["focus"] = f"{type(erro).__name__}: {erro}"
    try:
        selic = obter_serie(config.SERIES_BCB["selic_meta"], 1)
        macro["selic_meta"] = float(selic["valor"].iloc[-1]) / 100.0
    except Exception as erro:  # noqa: BLE001
        log.warning("Falha ao obter Selic no BCB: %s", erro)
        macro["erros"]["selic"] = f"{type(erro).__name__}: {erro}"
    try:
        cdi = obter_serie_periodo(config.SERIES_BCB["cdi_diario"], 365)
        if cdi.empty:
            raise ValueError("série vazia")
        macro["cdi_12m"] = acumular(cdi)
        macro["fonte_cdi"] = "BCB 12 (acumulado dos últimos 12 meses)"
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
    macro["juro_real_selic"] = juro_real(macro["selic_meta"], macro["ipca_12m"])
    macro["juro_real_cdi"] = juro_real(macro["cdi_12m"], macro["ipca_12m"])
    return macro

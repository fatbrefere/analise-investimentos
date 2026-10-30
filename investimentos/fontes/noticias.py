"""
Notícias recentes por empresa e de mercado, via RSS do Google Notícias
(gratuito, sem chave). Cada consulta devolve manchetes com fonte e data.
"""
from __future__ import annotations

import logging
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import requests

from investimentos import config

log = logging.getLogger(__name__)

URL_RSS = "https://news.google.com/rss/search?q={consulta}&hl={hl}&gl={gl}&ceid={ceid}"
LOCAIS = {
    "BR": {"hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-150"},
    "US": {"hl": "en-US", "gl": "US", "ceid": "US:en"},
}

CONSULTAS_MERCADO_BR = ["Selic Copom", "Ibovespa bolsa", "dólar câmbio", "inflação IPCA", "economia Brasil governo"]
CONSULTAS_MERCADO_US = ["Federal Reserve rates", "S&P 500 stocks", "US economy"]


def parse_rss(xml_texto: str, maximo: int = 8, dias: int = 21) -> list[dict]:
    """Extrai manchetes de um feed RSS do Google Notícias (função pura, testável)."""
    raiz = ET.fromstring(xml_texto)
    limite = datetime.now(timezone.utc) - timedelta(days=dias)
    itens = []
    for item in raiz.iter("item"):
        titulo = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        fonte = (item.findtext("source") or "").strip()
        data_txt = item.findtext("pubDate") or ""
        try:
            data = parsedate_to_datetime(data_txt)
            if data.tzinfo is None:
                data = data.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            data = None
        if data is not None and data < limite:
            continue
        if not titulo:
            continue
        # O Google põe " - Fonte" no fim do título
        if fonte and titulo.endswith(f" - {fonte}"):
            titulo = titulo[: -len(fonte) - 3].strip()
        itens.append({"titulo": titulo, "fonte": fonte, "data": data.date().isoformat() if data else None, "link": link})
        if len(itens) >= maximo:
            break
    return itens


def buscar(consulta: str, pais: str = "BR", maximo: int = 8, dias: int = 21) -> list[dict]:
    local = LOCAIS.get(pais, LOCAIS["BR"])
    url = URL_RSS.format(consulta=quote(consulta), **local)
    resposta = requests.get(url, headers=config.HTTP_HEADERS, timeout=config.HTTP_TIMEOUT)
    resposta.raise_for_status()
    return parse_rss(resposta.text, maximo=maximo, dias=dias)


def _nome_curto(nome: str | None, ticker: str) -> str:
    """'MARCOPOLO ON' -> 'Marcopolo'; 'JHSF Part ON NM' -> 'JHSF Part'."""
    if not nome:
        return ticker
    palavras = [p for p in str(nome).split() if p.upper() not in ("ON", "PN", "PNA", "PNB", "UNT", "NM", "N1", "N2", "MA", "ED", "EJ", "EB", "DR3", "SA", "S.A.", "S/A", "INC.", "INC", "CORP", "CORP.")]
    return " ".join(palavras).title() if palavras else ticker


def noticias_por_empresa(tickers: list[tuple[str, str | None, str]], maximo: int = 6, pausa: float = 0.5) -> dict[str, list[dict]]:
    """Para cada (ticker, nome, pais) devolve as manchetes recentes. Falhas não interrompem."""
    resultado: dict[str, list[dict]] = {}
    for i, (ticker, nome, pais) in enumerate(tickers):
        if i:
            time.sleep(pausa)
        consulta = f'"{_nome_curto(nome, ticker)}" OR {ticker}' if nome else ticker
        if pais == "BR":
            consulta += " ações"
        else:
            consulta += " stock"
        try:
            resultado[ticker] = buscar(consulta, pais=pais, maximo=maximo)
        except Exception as erro:  # noqa: BLE001
            log.warning("Sem notícias para %s: %s", ticker, erro)
            resultado[ticker] = []
    return resultado


def noticias_de_mercado(maximo_por_tema: int = 5, pausa: float = 0.5) -> dict[str, list[dict]]:
    temas: dict[str, list[dict]] = {}
    for pais, consultas in (("BR", CONSULTAS_MERCADO_BR), ("US", CONSULTAS_MERCADO_US)):
        for consulta in consultas:
            try:
                temas[f"{pais}: {consulta}"] = buscar(consulta, pais=pais, maximo=maximo_por_tema, dias=7)
            except Exception as erro:  # noqa: BLE001
                log.warning("Sem notícias de mercado para '%s': %s", consulta, erro)
                temas[f"{pais}: {consulta}"] = []
            time.sleep(pausa)
    return temas

"""
Fonte de dados via Yahoo Finance (biblioteca yfinance).

Usada para:
- fundamentos de ações americanas (lista em config.TICKERS_US);
- cotações de ETFs (EUA e Brasil), do câmbio e de qualquer ticker da carteira;
- histórico de preços para gráficos.
"""
from __future__ import annotations

import logging
import math

import pandas as pd

from investimentos import config
from investimentos.fontes.comum import completar_colunas, derivar_por_acao

log = logging.getLogger(__name__)


def _yf():
    import yfinance as yf  # import tardio: só carrega quando realmente usado
    return yf


def _num(valor, escala: float = 1.0) -> float:
    try:
        if valor is None:
            return math.nan
        numero = float(valor)
    except (TypeError, ValueError):
        return math.nan
    if math.isinf(numero):
        return math.nan
    return numero * escala


def _primeiro_valor(df: pd.DataFrame | None, *rotulos: str) -> float:
    """Pega o valor mais recente de uma linha de um demonstrativo do yfinance."""
    if df is None or df.empty:
        return math.nan
    for rotulo in rotulos:
        if rotulo in df.index:
            serie = df.loc[rotulo].dropna()
            if not serie.empty:
                return _num(serie.iloc[0])
    return math.nan


def normalizar_info(ticker: str, info: dict, dre: pd.DataFrame | None = None, balanco: pd.DataFrame | None = None) -> dict:
    """Transforma o dicionário `info` do yfinance (+ DRE e balanço) no esquema comum.

    Função pura, separada da rede, para poder ser testada com dados sintéticos.
    """
    info = info or {}
    preco = _num(info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose"))
    dpa = _num(info.get("trailingAnnualDividendRate"))
    dy = dpa / preco if preco and not math.isnan(dpa) and preco > 0 else math.nan

    ebit = _primeiro_valor(dre, "EBIT", "Operating Income")
    ebitda = _num(info.get("ebitda"))
    if math.isnan(ebitda):
        ebitda = _primeiro_valor(dre, "EBITDA", "Normalized EBITDA")
    receita = _num(info.get("totalRevenue"))
    if math.isnan(receita):
        receita = _primeiro_valor(dre, "Total Revenue", "Operating Revenue")
    lucro = _primeiro_valor(dre, "Net Income", "Net Income Common Stockholders")
    imposto = _primeiro_valor(dre, "Tax Rate For Calcs")
    if math.isnan(imposto) or imposto <= 0 or imposto >= 1:
        imposto = 0.21  # alíquota federal padrão dos EUA

    ev = _num(info.get("enterpriseValue"))
    divida_total = _num(info.get("totalDebt"))
    if math.isnan(divida_total):
        divida_total = _primeiro_valor(balanco, "Total Debt")
    patrimonio = _primeiro_valor(balanco, "Stockholders Equity", "Common Stock Equity", "Total Equity Gross Minority Interest")
    caixa = _num(info.get("totalCash"))
    if math.isnan(caixa):
        caixa = _primeiro_valor(balanco, "Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments")

    ev_ebit = ev / ebit if ev and ebit and not math.isnan(ebit) and ebit != 0 else math.nan
    ev_ebitda = _num(info.get("enterpriseToEbitda"))
    if math.isnan(ev_ebitda) and ev and ebitda and not math.isnan(ebitda) and ebitda != 0:
        ev_ebitda = ev / ebitda

    # ROIC = EBIT x (1 - imposto) / (dívida + patrimônio - caixa)
    capital_investido = math.nan
    if not math.isnan(patrimonio):
        capital_investido = patrimonio + (0 if math.isnan(divida_total) else divida_total) - (0 if math.isnan(caixa) else caixa)
    roic = ebit * (1 - imposto) / capital_investido if not math.isnan(ebit) and capital_investido and capital_investido > 0 else math.nan

    margem_ebit = ebit / receita if receita and not math.isnan(ebit) and receita > 0 else math.nan
    margem_liquida = _num(info.get("profitMargins"))
    if math.isnan(margem_liquida) and receita and not math.isnan(lucro) and receita > 0:
        margem_liquida = lucro / receita

    divida_patrimonio = _num(info.get("debtToEquity"), escala=0.01)  # yfinance devolve em %
    if math.isnan(divida_patrimonio) and patrimonio and not math.isnan(divida_total) and patrimonio > 0:
        divida_patrimonio = divida_total / patrimonio

    pvp = _num(info.get("priceToBook"))
    vpa = _num(info.get("bookValue"))
    # O Yahoo às vezes devolve bookValue/priceToBook em escala errada (ex.: BRK-B
    # com P/VP 0,001). Um P/VP positivo abaixo de 0,05 é lixo, não pechincha.
    if not math.isnan(pvp) and 0 < pvp < 0.05:
        pvp = math.nan
        vpa = math.nan

    return {
        "ticker": ticker,
        "nome": info.get("longName") or info.get("shortName"),
        "pais": "US",
        "moeda": info.get("currency") or "USD",
        "setor": info.get("sector"),
        "preco": preco,
        "pl": _num(info.get("trailingPE")),
        "pvp": pvp,
        "dy": dy,
        "ev_ebit": ev_ebit,
        "ev_ebitda": ev_ebitda,
        "roic": roic,
        "roe": _num(info.get("returnOnEquity")),
        "margem_ebit": margem_ebit,
        "margem_liquida": margem_liquida,
        "liquidez_corrente": _num(info.get("currentRatio")),
        "divida_patrimonio": divida_patrimonio,
        # yfinance só traz crescimento anual; usamos como aproximação do campo "5 anos"
        "cresc_receita_5a": _num(info.get("revenueGrowth")),
        "liquidez": _num(info.get("averageVolume")) * (preco if not math.isnan(preco) else math.nan),
        "patrimonio_liquido": patrimonio,
        "lpa": _num(info.get("trailingEps")),
        "vpa": vpa,
        "dpa": dpa,
    }


def obter_fundamentos_us(tickers: list[str] | None = None, com_demonstrativos: bool = True) -> pd.DataFrame:
    """Baixa fundamentos das ações americanas da lista configurada."""
    yf = _yf()
    tickers = tickers or config.TICKERS_US
    linhas = []
    for ticker in tickers:
        try:
            acao = yf.Ticker(ticker)
            info = acao.info or {}
            dre = balanco = None
            if com_demonstrativos:
                try:
                    dre = acao.income_stmt
                    balanco = acao.balance_sheet
                except Exception as erro:  # noqa: BLE001
                    log.debug("Sem demonstrativos para %s: %s", ticker, erro)
            linhas.append(normalizar_info(ticker, info, dre, balanco))
        except Exception as erro:  # noqa: BLE001 - segue para o próximo papel
            log.warning("Falha ao obter %s no Yahoo Finance: %s", ticker, erro)
    df = pd.DataFrame(linhas)
    if df.empty:
        return completar_colunas(df)
    df = completar_colunas(df)
    df = derivar_por_acao(df)
    log.info("Yahoo Finance: %d ações americanas carregadas.", len(df))
    return df


def ticker_yahoo(ticker: str, pais: str | None = None) -> str:
    """Converte um código da B3 para o formato do Yahoo (PETR4 -> PETR4.SA)."""
    ticker = ticker.strip().upper()
    if "." in ticker or "=" in ticker or "-" in ticker:
        return ticker
    if pais == "US":
        return ticker
    # Códigos da B3: 4 letras + 1 ou 2 dígitos (PETR4, BOVA11, MXRF11)
    if len(ticker) >= 5 and ticker[:4].isalpha() and ticker[4:].isdigit():
        return f"{ticker}.SA"
    return ticker


def obter_cotacoes(tickers_yahoo: list[str]) -> pd.DataFrame:
    """Último preço de fechamento para uma lista de tickers no formato do Yahoo."""
    yf = _yf()
    tickers_yahoo = list(dict.fromkeys(t for t in tickers_yahoo if t))
    if not tickers_yahoo:
        return pd.DataFrame(columns=["ticker_yahoo", "preco", "data"])
    dados = yf.download(tickers_yahoo, period="10d", interval="1d", progress=False, auto_adjust=True, group_by="ticker", threads=True)
    linhas = []
    for ticker in tickers_yahoo:
        try:
            serie = dados[ticker]["Close"] if len(tickers_yahoo) > 1 else dados["Close"]
            serie = serie.dropna()
            if serie.empty:
                continue
            linhas.append({"ticker_yahoo": ticker, "preco": float(serie.iloc[-1]), "data": serie.index[-1].date()})
        except (KeyError, TypeError):
            log.warning("Sem cotação para %s", ticker)
    return pd.DataFrame(linhas, columns=["ticker_yahoo", "preco", "data"])


def obter_dolar() -> float:
    """Cotação USD/BRL pelo Yahoo (usada como reserva quando o Banco Central falha)."""
    cot = obter_cotacoes(["BRL=X"])
    return float(cot["preco"].iloc[0]) if not cot.empty else math.nan


def obter_historico(ticker_yahoo: str, periodo: str = "5y") -> pd.DataFrame:
    yf = _yf()
    hist = yf.Ticker(ticker_yahoo).history(period=periodo, auto_adjust=True)
    if hist is None or hist.empty:
        return pd.DataFrame(columns=["data", "preco"])
    hist = hist.reset_index()
    return pd.DataFrame({"data": pd.to_datetime(hist["Date"]).dt.date, "preco": hist["Close"].astype(float)})

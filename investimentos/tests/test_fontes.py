import math

import pandas as pd
import pytest

from investimentos.fontes import bcb, fundamentus, yahoo
from investimentos.fontes.comum import COLUNAS_FUNDAMENTOS, numero_br
from investimentos.tests.fixtures_fundamentus import html_detalhes, html_resultado


@pytest.mark.parametrize("entrada,esperado", [
    ("12,34", 12.34),
    ("1.234,56", 1234.56),
    ("15,20%", 0.152),
    ("-3,10", -3.10),
    ("380.000.000.000", 380_000_000_000.0),
    ("-", math.nan),
    ("", math.nan),
    (None, math.nan),
    (7, 7.0),
])
def test_numero_br(entrada, esperado):
    resultado = numero_br(entrada)
    if isinstance(esperado, float) and math.isnan(esperado):
        assert math.isnan(resultado)
    else:
        assert resultado == pytest.approx(esperado)


def test_parse_resultado_fundamentus():
    df = fundamentus.parse_resultado(html_resultado())
    assert list(df.columns) == COLUNAS_FUNDAMENTOS
    assert len(df) == 8
    petr = df.set_index("ticker").loc["PETR4"]
    assert petr["preco"] == pytest.approx(32.5)
    assert petr["pl"] == pytest.approx(4.1)
    assert petr["dy"] == pytest.approx(0.152)
    assert petr["roic"] == pytest.approx(0.253)
    assert petr["liquidez"] == pytest.approx(1_500_000_000.0)
    assert petr["patrimonio_liquido"] == pytest.approx(380_000_000_000.0)
    assert petr["divida_patrimonio"] == pytest.approx(0.70)
    assert petr["pais"] == "BR" and petr["moeda"] == "BRL"
    # derivados por ação
    assert petr["lpa"] == pytest.approx(32.5 / 4.1)
    assert petr["vpa"] == pytest.approx(32.5 / 1.05)
    assert petr["dpa"] == pytest.approx(32.5 * 0.152)
    # linha sem dados vira NaN, sem quebrar
    assert math.isnan(df.set_index("ticker").loc["SANB11"]["preco"])
    # prejuízo: P/L negativo gera LPA negativo
    assert df.set_index("ticker").loc["MGLU3"]["lpa"] < 0


def test_parse_detalhes_fundamentus():
    dados = fundamentus.parse_detalhes(html_detalhes())
    assert dados["nome"] == "PETROBRAS PN"
    assert dados["setor"] == "Petróleo, Gás e Biocombustíveis"
    assert dados["subsetor"] == "Exploração, Refino e Distribuição"


@pytest.mark.parametrize("setor,subsetor,esperado", [
    ("Intermediários Financeiros", "Bancos", "Bancos"),
    ("Utilidade Pública", "Energia Elétrica", "Energia"),
    ("Utilidade Pública", "Água e Saneamento", "Saneamento"),
    ("Previdência e Seguros", "Seguradoras", "Seguros"),
    ("Telecomunicações", "Telecomunicações", "Telecom"),
    ("Petróleo, Gás e Biocombustíveis", "Exploração", None),
    (None, None, None),
])
def test_classificar_setor_barsi(setor, subsetor, esperado):
    assert fundamentus.classificar_setor_barsi(setor, subsetor) == esperado


def test_obter_setores_usa_cache(tmp_path, monkeypatch):
    cache = tmp_path / "setores.csv"
    pd.DataFrame([{"ticker": "PETR4", "nome": "PETROBRAS", "setor": "Petróleo", "subsetor": "Exploração"}]).to_csv(cache, index=False)
    chamadas = []

    def falso_baixar(url):
        chamadas.append(url)
        return html_detalhes()

    monkeypatch.setattr(fundamentus, "baixar_html", falso_baixar)
    resultado = fundamentus.obter_setores_br(["PETR4", "ITSA4"], caminho=cache)
    assert chamadas == [fundamentus.URL_DETALHES.format(ticker="ITSA4")]
    assert set(resultado["ticker"]) == {"PETR4", "ITSA4"}
    # segunda chamada: tudo em cache
    chamadas.clear()
    fundamentus.obter_setores_br(["PETR4", "ITSA4"], caminho=cache)
    assert chamadas == []


def test_normalizar_info_yahoo():
    info = {
        "longName": "Apple Inc.", "sector": "Technology", "currency": "USD",
        "currentPrice": 200.0, "trailingPE": 30.0, "priceToBook": 45.0,
        "trailingAnnualDividendRate": 1.0, "enterpriseValue": 3_000e9, "ebitda": 130e9,
        "returnOnEquity": 1.5, "profitMargins": 0.25, "currentRatio": 0.9,
        "debtToEquity": 150.0, "revenueGrowth": 0.05, "averageVolume": 50e6,
        "trailingEps": 6.5, "bookValue": 4.4, "totalDebt": 100e9, "totalCash": 60e9,
    }
    dre = pd.DataFrame({"2025": [120e9, 400e9, 100e9, 0.15]}, index=["EBIT", "Total Revenue", "Net Income", "Tax Rate For Calcs"])
    balanco = pd.DataFrame({"2025": [70e9]}, index=["Stockholders Equity"])
    linha = yahoo.normalizar_info("AAPL", info, dre, balanco)
    assert linha["pais"] == "US" and linha["moeda"] == "USD"
    assert linha["dy"] == pytest.approx(1.0 / 200.0)
    assert linha["ev_ebit"] == pytest.approx(3_000e9 / 120e9)
    assert linha["divida_patrimonio"] == pytest.approx(1.5)
    # ROIC = EBIT * (1 - 0.15) / (70 + 100 - 60) bi
    assert linha["roic"] == pytest.approx(120e9 * 0.85 / 110e9)
    assert linha["margem_ebit"] == pytest.approx(0.3)
    assert linha["liquidez"] == pytest.approx(50e6 * 200.0)
    assert linha["cresc_receita_5a"] == pytest.approx(0.05)


def test_normalizar_info_yahoo_sem_dados():
    linha = yahoo.normalizar_info("XXXX", {}, None, None)
    assert linha["ticker"] == "XXXX"
    assert all(math.isnan(linha[c]) for c in ("preco", "pl", "dy", "ev_ebit", "roic"))


@pytest.mark.parametrize("ticker,pais,esperado", [
    ("PETR4", "BR", "PETR4.SA"),
    ("petr4", None, "PETR4.SA"),
    ("MXRF11", None, "MXRF11.SA"),
    ("AAPL", "US", "AAPL"),
    ("AAPL", None, "AAPL"),
    ("BRK-B", None, "BRK-B"),
    ("BRL=X", None, "BRL=X"),
    ("VALE3.SA", None, "VALE3.SA"),
])
def test_ticker_yahoo(ticker, pais, esperado):
    assert yahoo.ticker_yahoo(ticker, pais) == esperado


def test_bcb_serie_e_acumulado():
    registros = [{"data": "01/01/2026", "valor": "0,50"}, {"data": "01/02/2026", "valor": "1.00"}, {"data": "01/03/2026", "valor": "0.25"}]
    df = bcb.serie_para_dataframe(registros)
    assert list(df["valor"]) == [0.5, 1.0, 0.25]
    assert bcb.acumular(df) == pytest.approx(1.005 * 1.01 * 1.0025 - 1)
    assert bcb.acumular(df, ultimos=1) == pytest.approx(0.0025)
    assert math.isnan(bcb.acumular(bcb.serie_para_dataframe([])))

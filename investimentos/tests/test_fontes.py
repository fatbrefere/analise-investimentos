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
    monkeypatch.setattr(fundamentus.config, "PAUSA_ENTRE_REQUISICOES", 0)
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


def test_normalizar_info_yahoo_descarta_pvp_com_escala_errada():
    linha = yahoo.normalizar_info("BRK-B", {"currentPrice": 548.0, "priceToBook": 0.00105, "bookValue": 522225.9})
    assert math.isnan(linha["pvp"]) and math.isnan(linha["vpa"])
    linha = yahoo.normalizar_info("MCD", {"currentPrice": 300.0, "priceToBook": -60.0, "bookValue": -5.0})
    assert linha["pvp"] == -60.0   # patrimônio negativo é informação real, fica


def test_bcb_cdi_acumula_serie_diaria_por_periodo(monkeypatch):
    def falsa_serie(codigo, ultimos):
        valores = {433: [{"data": f"01/{m:02d}/2026", "valor": "0.40"} for m in range(1, 13)],
                   432: [{"data": "01/10/2026", "valor": "13.75"}], 1: [{"data": "24/10/2026", "valor": "5.50"}]}[codigo]
        return bcb.serie_para_dataframe(valores[-ultimos:])

    chamadas = []

    def falsa_periodo(codigo, dias):
        chamadas.append((codigo, dias))
        return bcb.serie_para_dataframe([{"data": f"{d:02d}/10/2026", "valor": "0.05"} for d in range(1, 11)])

    monkeypatch.setattr(bcb, "obter_serie", falsa_serie)
    monkeypatch.setattr(bcb, "obter_serie_periodo", falsa_periodo)
    macro = bcb.obter_macro()
    assert chamadas == [(12, 365)]
    assert macro["cdi_12m"] == pytest.approx(1.0005 ** 10 - 1)
    assert macro["erros"] == {}


def test_bcb_cdi_usa_reserva_anualizada(monkeypatch):
    def falsa_periodo(codigo, dias):
        raise ConnectionError("fora do ar")

    monkeypatch.setattr(bcb, "obter_serie_periodo", falsa_periodo)

    def falsa_serie(codigo, ultimos):
        if codigo == 12:
            raise ConnectionError("fora do ar")
        valores = {433: [{"data": f"01/{m:02d}/2026", "valor": "0.40"} for m in range(1, 13)],
                   432: [{"data": "01/10/2026", "valor": "13.75"}],
                   4389: [{"data": "24/10/2026", "valor": "13.65"}],
                   1: [{"data": "24/10/2026", "valor": "5.50"}]}[codigo]
        return bcb.serie_para_dataframe(valores[-ultimos:])

    monkeypatch.setattr(bcb, "obter_serie", falsa_serie)
    macro = bcb.obter_macro()
    assert macro["cdi_12m"] == pytest.approx(0.1365)
    assert "4389" in macro["fonte_cdi"]
    assert "cdi_diario" in macro["erros"]
    assert macro["selic_meta"] == pytest.approx(0.1375)


def test_obter_setores_aborta_apos_falhas_seguidas(tmp_path, monkeypatch):
    def quebra(url):
        raise ConnectionError("403")

    monkeypatch.setattr(fundamentus, "baixar_html", quebra)
    monkeypatch.setattr(fundamentus.config, "PAUSA_ENTRE_REQUISICOES", 0)
    with pytest.raises(RuntimeError):
        fundamentus.obter_setores_br([f"T{i}" for i in range(10)], caminho=tmp_path / "s.csv")

"""Teste do pipeline completo com todas as fontes de rede substituídas por dados sintéticos."""
import json
import math

import pandas as pd

from investimentos import atualizar, config
from investimentos.fontes import bcb, fundamentus, yahoo
from investimentos.tests.fixtures_fundamentus import html_detalhes, html_resultado


def test_pipeline_offline(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PASTA_DADOS", tmp_path)
    monkeypatch.setattr(config, "PASTA_HISTORICO", tmp_path / "historico")
    monkeypatch.setattr(fundamentus, "ARQUIVO_CACHE_SETORES", tmp_path / "setores_br.csv")
    monkeypatch.setattr(config, "PAUSA_ENTRE_REQUISICOES", 0)
    for nome in ("ARQ_FUNDAMENTOS", "ARQ_RANKING", "ARQ_MACRO", "ARQ_COTACOES", "ARQ_STATUS"):
        monkeypatch.setattr(atualizar, nome, tmp_path / getattr(atualizar, nome).name)

    def falso_baixar(url=fundamentus.URL_RESULTADO):
        return html_resultado() if url == fundamentus.URL_RESULTADO else html_detalhes()

    monkeypatch.setattr(fundamentus, "baixar_html", falso_baixar)

    def falso_us(tickers=None, com_demonstrativos=True):
        linhas = [yahoo.normalizar_info("AAPL", {"currentPrice": 200.0, "trailingPE": 30.0, "priceToBook": 45.0, "trailingAnnualDividendRate": 1.0, "returnOnEquity": 1.5, "profitMargins": 0.25, "averageVolume": 50e6, "trailingEps": 6.5, "bookValue": 4.4}),
                  yahoo.normalizar_info("JNJ", {"currentPrice": 150.0, "trailingPE": 14.0, "priceToBook": 1.4, "trailingAnnualDividendRate": 9.5, "returnOnEquity": 0.20, "profitMargins": 0.18, "averageVolume": 10e6, "debtToEquity": 40.0, "revenueGrowth": 0.04, "currentRatio": 1.6})]
        from investimentos.fontes.comum import completar_colunas, derivar_por_acao
        return derivar_por_acao(completar_colunas(pd.DataFrame(linhas)))

    monkeypatch.setattr(yahoo, "obter_fundamentos_us", falso_us)

    def falsa_serie(codigo, ultimos):
        valores = {433: [{"data": f"01/{m:02d}/2026", "valor": "0.40"} for m in range(1, 13)],
                   432: [{"data": "01/10/2026", "valor": "10.50"}],
                   12: [{"data": "01/10/2026", "valor": "0.04"}] * 252,
                   1: [{"data": "24/10/2026", "valor": "5.20"}]}[codigo]
        return bcb.serie_para_dataframe(valores[-ultimos:])

    monkeypatch.setattr(bcb, "obter_serie", falsa_serie)
    monkeypatch.setattr(bcb, "obter_serie_periodo", lambda codigo, dias: falsa_serie(codigo, 252))

    def falsas_cotacoes(tickers_yahoo):
        return pd.DataFrame([{"ticker_yahoo": t, "preco": 100.0, "data": "2026-10-24"} for t in tickers_yahoo])

    monkeypatch.setattr(yahoo, "obter_cotacoes", falsas_cotacoes)

    status = atualizar.executar()

    assert all(v["ok"] for v in status["etapas"].values()), status["etapas"]
    assert status["papeis_br"] == 8 and status["papeis_us"] == 2
    assert status["taxa_minima_atratividade"] == 0.105   # Selic > IPCA (4,9%) + 5%

    fund = pd.read_csv(tmp_path / "fundamentos.csv")
    assert set(fund["pais"]) == {"BR", "US"}
    assert fund.set_index("ticker").loc["PETR4", "setor_barsi"] != "Energia"
    assert fund.set_index("ticker").loc["PETR4", "nome"] == "PETROBRAS PN"

    ranking = pd.read_csv(tmp_path / "ranking.csv")
    assert "JNJ" in set(ranking["ticker"])          # volume 1,5 bi > mínimo
    assert "ILIQ3" not in set(ranking["ticker"])
    # JNJ passa em 6 dos 7 critérios de Graham (preço justo ~160,7 dá só 7% de margem)
    assert ranking.set_index("ticker").loc["JNJ", "pontos_graham"] == 6

    macro = json.loads((tmp_path / "macro.json").read_text(encoding="utf-8"))
    assert math.isclose(macro["ipca_12m"], 1.004 ** 12 - 1)
    assert macro["erros"] == {}
    assert status["avisos"] == []
    assert status["setores_br_em_cache"] > 0
    assert (tmp_path / "setores_br.csv").exists()
    assert macro["selic_meta"] == 0.105 and macro["dolar"] == 5.2

    cot = pd.read_csv(tmp_path / "cotacoes.csv")
    assert "VOO" in set(cot["ticker"]) and "BOVA11" in set(cot["ticker"])
    assert cot.set_index("ticker").loc["BOVA11", "ticker_yahoo"] == "BOVA11.SA"
    # carteira de exemplo: MXRF11 não está nos fundamentos -> cotação pedida
    assert "MXRF11" in set(cot["ticker"])

    assert len(list((tmp_path / "historico").glob("ranking_*.csv"))) == 1


def test_pipeline_usa_dados_anteriores_quando_fonte_falha(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PASTA_DADOS", tmp_path)
    monkeypatch.setattr(config, "PASTA_HISTORICO", tmp_path / "historico")
    for nome in ("ARQ_FUNDAMENTOS", "ARQ_RANKING", "ARQ_MACRO", "ARQ_COTACOES", "ARQ_STATUS"):
        monkeypatch.setattr(atualizar, nome, tmp_path / getattr(atualizar, nome).name)
    fundamentus.parse_resultado(html_resultado()).to_csv(tmp_path / "fundamentos.csv", index=False)

    def quebra(*args, **kwargs):
        raise ConnectionError("fora do ar")

    monkeypatch.setattr(fundamentus, "baixar_html", quebra)
    monkeypatch.setattr(bcb, "obter_serie", quebra)
    monkeypatch.setattr(bcb, "obter_serie_periodo", quebra)
    monkeypatch.setattr(yahoo, "obter_cotacoes", quebra)

    status = atualizar.executar(incluir_us=False, incluir_setores=False)
    assert not status["etapas"]["fundamentus"]["ok"]
    assert any("fundamentus" in a.lower() or "fora do ar" in a for a in status["avisos"])
    texto = (tmp_path / "macro.json").read_text(encoding="utf-8")
    assert "NaN" not in texto                       # JSON válido: null em vez de NaN
    json.loads(texto)
    assert status["papeis_br"] == 8                      # veio do arquivo anterior
    assert (tmp_path / "ranking.csv").exists()

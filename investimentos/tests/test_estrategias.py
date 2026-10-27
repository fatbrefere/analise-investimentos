import math

import pandas as pd
import pytest

from investimentos import estrategias
from investimentos.fontes import fundamentus
from investimentos.tests.fixtures_fundamentus import html_resultado


@pytest.fixture
def base():
    df = fundamentus.parse_resultado(html_resultado())
    return estrategias.filtrar_liquidez(df)


def test_filtrar_liquidez_remove_iliquidas_e_sem_preco(base):
    tickers = set(base["ticker"])
    assert "ILIQ3" not in tickers      # liquidez 50 mil < 1 milhão
    assert "SANB11" not in tickers     # sem preço
    assert "PETR4" in tickers


def test_formula_magica_ordena_por_ev_ebit_e_roic(base):
    m = estrategias.formula_magica(base, top_n=3)
    # MGLU3 (EV/EBIT negativo) e BBAS3 (EV/EBIT zero) ficam de fora
    assert set(m["ticker"]).isdisjoint({"MGLU3", "BBAS3"})
    assert m.iloc[0]["ticker"] == "PETR4"  # EV/EBIT 3,5 e ROIC 25% -> melhor soma de ranks
    assert m["posicao_magica"].tolist() == list(range(1, len(m) + 1))
    assert m["aprovado_magica"].sum() == 3


def test_preco_justo_graham():
    assert estrategias.preco_justo_graham(2.0, 10.0) == pytest.approx(math.sqrt(22.5 * 2 * 10))
    assert math.isnan(estrategias.preco_justo_graham(-1.0, 10.0))
    assert math.isnan(estrategias.preco_justo_graham(2.0, float("nan")))


def test_graham_aprova_barata_e_reprova_cara(base):
    g = estrategias.graham(base).set_index("ticker")
    assert g.loc["ITSA4", "aprovado_graham"]
    assert not g.loc["WEGE3", "aprovado_graham"]   # P/L 30 e P/VP 8
    assert not g.loc["MGLU3", "aprovado_graham"]   # prejuízo
    assert g.loc["ITSA4", "margem_seguranca_graham"] > 0.2
    assert g.loc["PETR4", "g_liquidez_corrente"] == False  # 0,95 < 1,5  # noqa: E712


def test_preco_teto_bazin():
    assert estrategias.preco_teto_bazin(3.0) == pytest.approx(50.0)
    assert math.isnan(estrategias.preco_teto_bazin(0.0))


def test_dividendos_bazin(base):
    base = base.copy()
    base["setor_barsi"] = base["ticker"].map({"TAEE11": "Energia"})
    d = estrategias.dividendos(base).set_index("ticker")
    assert d.loc["PETR4", "aprovado_dividendos"]
    assert d.loc["TAEE11", "aprovado_dividendos"]
    assert not d.loc["WEGE3", "aprovado_dividendos"]  # DY 1,2%
    assert not d.loc["MGLU3", "aprovado_dividendos"]
    # preço teto = DPA / 6%; PETR4 DPA = 32,5 * 15,2%
    assert d.loc["PETR4", "preco_teto_bazin"] == pytest.approx(32.5 * 0.152 / 0.06)
    assert d.loc["TAEE11", "pontos_dividendos"] == pytest.approx(4.5)   # 4 critérios + setor perene
    assert d.loc["PETR4", "pontos_dividendos"] == pytest.approx(4.0)


def test_buffett_qualidade(base):
    b = estrategias.buffett(base).set_index("ticker")
    assert b.loc["ITSA4", "aprovado_buffett"]
    assert not b.loc["WEGE3", "aprovado_buffett"]   # P/L 30 > 20 e P/VP 8 > 3
    assert not b.loc["PETR4", "aprovado_buffett"]   # dívida/PL 0,7 > 0,5
    assert b.loc["WEGE3", "pontos_buffett"] == 4


def test_taxa_minima_atratividade():
    assert estrategias.taxa_minima_atratividade(0.045, premio=0.05, selic=0.10) == pytest.approx(0.10)
    assert estrategias.taxa_minima_atratividade(0.08, premio=0.05, selic=0.10) == pytest.approx(0.13)
    assert estrategias.taxa_minima_atratividade(float("nan"), selic=0.10) == pytest.approx(0.10)
    assert math.isnan(estrategias.taxa_minima_atratividade(float("nan")))


def test_consolidar(base):
    r = estrategias.consolidar(base, taxa_minima=0.12)
    assert len(r) == len(base)
    assert set(r["ticker"]) == set(base["ticker"])
    r = r.set_index("ticker")
    assert r.loc["ITSA4", "qtd_estrategias_aprovado"] >= 3   # Graham, Dividendos, Buffett (e Mágica)
    assert "Graham" in r.loc["ITSA4", "estrategias_aprovado"]
    assert r.loc["MGLU3", "qtd_estrategias_aprovado"] == 0
    assert r.loc["PETR4", "earnings_yield"] == pytest.approx(1 / 4.1)
    assert bool(r.loc["PETR4", "bate_inflacao"]) is True
    assert bool(r.loc["WEGE3", "bate_inflacao"]) is False
    # ordenado por pontuação
    assert r["pontuacao_geral"].is_monotonic_decreasing


def test_consolidar_com_parametros(base):
    r = estrategias.consolidar(base, parametros={"dividendos": {"dy_minimo": 0.20}}).set_index("ticker")
    assert not r["aprovado_dividendos"].any()


def test_consolidar_vazio():
    vazio = estrategias.filtrar_liquidez(fundamentus.parse_resultado(html_resultado()).iloc[0:0])
    assert estrategias.consolidar(vazio).empty

import math

import pandas as pd
import pytest

from investimentos import carteira as mod
from investimentos import config


def carteira_teste():
    return mod.normalizar_carteira(pd.DataFrame([
        {"ticker": "PETR4", "tipo": "Ação BR", "moeda": "BRL", "quantidade": 100, "preco_medio": 30.0},
        {"ticker": "AAPL", "tipo": "Ação US", "moeda": "USD", "quantidade": 10, "preco_medio": 150.0},
        {"ticker": "", "tipo": "Renda Fixa BR", "moeda": "BRL", "quantidade": 1, "preco_medio": 5000.0, "valor_atual": 5500.0},
        {"ticker": "ZZZZ3", "tipo": "Ação BR", "moeda": "BRL", "quantidade": 10, "preco_medio": 10.0},
    ]))


def test_carrega_exemplo():
    df = mod.carregar_carteira(config.ARQUIVO_CARTEIRA_EXEMPLO)
    assert not df.empty
    assert set(df["tipo"]) <= set(config.TIPOS_DE_ATIVO)


def test_tipo_desconhecido():
    with pytest.raises(ValueError):
        mod.normalizar_carteira(pd.DataFrame([{"ticker": "X", "tipo": "Bitcoin", "moeda": "BRL", "quantidade": 1, "preco_medio": 1}]))


def test_avaliar_carteira():
    df = mod.avaliar_carteira(carteira_teste(), {"PETR4": 40.0, "AAPL": 200.0}, dolar=5.0)
    df = df.set_index("ticker")
    assert df.loc["PETR4", "valor"] == pytest.approx(4000.0)
    assert df.loc["PETR4", "resultado_pct"] == pytest.approx(1 / 3)
    assert df.loc["AAPL", "valor_brl"] == pytest.approx(10 * 200 * 5.0)
    assert df.loc["", "valor_brl"] == pytest.approx(5500.0)       # valor informado
    assert df.loc["ZZZZ3", "valor"] == pytest.approx(100.0)       # sem cotação -> custo
    assert bool(df.loc["ZZZZ3", "sem_cotacao"]) is True
    res = mod.resumo(df.reset_index())
    assert res["valor_brl"] == pytest.approx(4000 + 10000 + 5500 + 100)
    assert res["sem_cotacao"] == 1


def test_alocacao_e_aporte():
    df = mod.avaliar_carteira(carteira_teste(), {"PETR4": 40.0, "AAPL": 200.0}, dolar=5.0)
    alvo = {"Ação BR": 0.5, "Ação US": 0.25, "Renda Fixa BR": 0.25}
    aloc = mod.alocacao(df, "tipo", alvo).set_index("tipo")
    total = df["valor_brl"].sum()
    assert aloc.loc["Ação US", "pct_atual"] == pytest.approx(10000 / total)
    assert aloc["pct_atual"].sum() == pytest.approx(1.0)
    assert aloc.loc["Ação US", "valor_para_alvo"] == pytest.approx(0.25 * total - 10000)

    aporte = mod.sugerir_aporte(df, 1000.0, alvo, "tipo")
    assert aporte["aporte_sugerido"].sum() == pytest.approx(1000.0)
    # Ação US está acima do alvo (51%): não recebe aporte
    assert "Ação US" not in set(aporte["tipo"])

    moeda = mod.alocacao(df, "moeda", {"BRL": 0.7, "USD": 0.3}).set_index("moeda")
    assert moeda.loc["USD", "pct_atual"] == pytest.approx(10000 / total)


def test_aporte_quando_ja_no_alvo():
    df = mod.avaliar_carteira(mod.normalizar_carteira(pd.DataFrame([
        {"ticker": "", "tipo": "Ação BR", "moeda": "BRL", "quantidade": 1, "preco_medio": 500, "valor_atual": 500},
        {"ticker": "", "tipo": "Caixa", "moeda": "BRL", "quantidade": 1, "preco_medio": 500, "valor_atual": 500},
    ])), {}, dolar=5.0)
    aporte = mod.sugerir_aporte(df, 100.0, {"Ação BR": 0.5, "Caixa": 0.5}, "tipo").set_index("tipo")
    assert aporte.loc["Ação BR", "aporte_sugerido"] == pytest.approx(50.0)


def test_dolar_desconhecido_nao_quebra():
    df = mod.avaliar_carteira(carteira_teste(), {"PETR4": 40.0, "AAPL": 200.0}, dolar=math.nan)
    assert math.isnan(df.set_index("ticker").loc["AAPL", "valor_brl"])

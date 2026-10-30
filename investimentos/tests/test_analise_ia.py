import json

import pandas as pd
import pytest

from investimentos import analise_ia, carteira, config, estrategias
from investimentos.fontes import fundamentus, noticias
from investimentos.tests.fixtures_fundamentus import html_resultado

RSS = """<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>x</title>
<item><title>Marcopolo lucra R$ 300 mi no 3T - Valor Econômico</title><link>https://ex/1</link>
<pubDate>Tue, 28 Oct 2026 12:00:00 GMT</pubDate><source url="https://valor.globo.com">Valor Econômico</source></item>
<item><title>Notícia velha - Fonte</title><link>https://ex/2</link><pubDate>Mon, 01 Jan 2024 12:00:00 GMT</pubDate><source url="x">Fonte</source></item>
<item><title>Sem data</title><link>https://ex/3</link></item>
</channel></rss>"""


def test_parse_rss(monkeypatch):
    from datetime import datetime, timezone

    class Agora(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 30, tzinfo=tz or timezone.utc)

    monkeypatch.setattr(noticias, "datetime", Agora)
    itens = noticias.parse_rss(RSS)
    assert [i["titulo"] for i in itens] == ["Marcopolo lucra R$ 300 mi no 3T", "Sem data"]
    assert itens[0] == {"titulo": "Marcopolo lucra R$ 300 mi no 3T", "fonte": "Valor Econômico", "data": "2026-10-28", "link": "https://ex/1"}


def test_nome_curto():
    assert noticias._nome_curto("MARCOPOLO ON", "POMO3") == "Marcopolo"
    assert noticias._nome_curto("JHSF Part ON NM", "JHSF3") == "Jhsf Part"
    assert noticias._nome_curto(None, "AAPL") == "AAPL"


def test_carteira_por_variavel_de_ambiente(monkeypatch):
    monkeypatch.setenv("CARTEIRA_CSV", "ticker,tipo,moeda,quantidade,preco_medio,valor_atual,descricao\nPOMO3,Ação BR,BRL,100,3.5,,Marcopolo\n")
    df = carteira.carregar_carteira()
    assert df["ticker"].tolist() == ["POMO3"]


class RespostaFalsa:
    def __init__(self, parsed):
        self.parsed_output = parsed
        self.stop_reason = "end_turn"
        self.stop_details = None


class ClienteFalso:
    """Imita client.messages.parse devolvendo análises coerentes com o pedido."""

    def __init__(self):
        self.chamadas = []
        self.messages = self

    def parse(self, **kwargs):
        self.chamadas.append(kwargs)
        conteudo = kwargs["messages"][0]["content"]
        if kwargs["output_format"] is analise_ia.LoteAnalise:
            pedidos = json.loads(conteudo.split("na mesma ordem:\n", 1)[1])
            papeis = [analise_ia.AnalisePapel(
                ticker=p["ticker"], classificacao="oportunidade" if p["ticker"] == "ITSA4" else "estudar", conviccao=4,
                resumo="r", tese="t", riscos=["a", "b", "c"], catalisadores=["x", "y"], barata_por_que="juros altos no Brasil",
                sensibilidade=analise_ia.Sensibilidade(juros=2, dolar=0, commodities=0, consumo=1, governo=0),
                o_que_acompanhar=["z"], noticias_relevantes="nada relevante") for p in pedidos]
            return RespostaFalsa(analise_ia.LoteAnalise(papeis=papeis))
        return RespostaFalsa(analise_ia.Panorama(resumo="panorama", temas=["juros"], setores_favorecidos=["bancos"], setores_pressionados=["varejo"],
                                                 alertas_carteira=[analise_ia.AlertaCarteira(ticker="PETR4", gravidade="atenção", mensagem="m")], sugestoes_diversificacao=["s"]))


@pytest.fixture
def dados(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PASTA_DADOS", tmp_path)
    monkeypatch.setattr(config, "PASTA_HISTORICO", tmp_path / "historico")
    monkeypatch.setattr(analise_ia, "ARQ_ANALISE", tmp_path / "analise_ia.json")
    base = estrategias.filtrar_liquidez(fundamentus.parse_resultado(html_resultado()))
    estrategias.consolidar(base, taxa_minima=0.12).to_csv(tmp_path / "ranking.csv", index=False)
    (tmp_path / "macro.json").write_text(json.dumps({"ipca_12m": 0.045, "selic_meta": 0.1375, "dolar": 5.5}), encoding="utf-8")
    monkeypatch.setenv("CARTEIRA_CSV", "ticker,tipo,moeda,quantidade,preco_medio,valor_atual,descricao\nPETR4,Ação BR,BRL,100,30,,Petro\nMGLU3,Ação BR,BRL,10,2,,Magalu\n")
    return tmp_path


def test_selecionar_universo_inclui_carteira(dados):
    ranking = pd.read_csv(dados / "ranking.csv")
    universo = analise_ia.selecionar_universo(ranking, carteira.carregar_carteira(), maximo=2)
    assert "MGLU3" in set(universo["ticker"])          # da carteira, mesmo reprovada em tudo
    assert universo.set_index("ticker").loc["MGLU3", "na_carteira"]
    assert len(universo) <= 2 + 2


def test_executar_com_cliente_falso(dados, monkeypatch):
    monkeypatch.setattr(analise_ia, "PAPEIS_POR_CHAMADA", 2)
    cliente = ClienteFalso()
    saida = analise_ia.executar(maximo=3, cliente=cliente, buscar_noticias=False)
    assert saida is not None
    tickers = {p["ticker"] for p in saida["papeis"]}
    assert {"PETR4", "MGLU3"} <= tickers
    assert saida["sem_analise"] == []
    assert saida["panorama"]["alertas_carteira"][0]["ticker"] == "PETR4"
    assert all(c["model"] == analise_ia.MODELO for c in cliente.chamadas)
    assert sum(1 for c in cliente.chamadas if c["output_format"] is analise_ia.LoteAnalise) >= 2   # lotes de 2
    gravado = json.loads((dados / "analise_ia.json").read_text(encoding="utf-8"))
    assert gravado["papeis"][0]["sensibilidade"]["juros"] == 2
    assert list((dados / "historico").glob("analise_ia_*.json"))


def test_executar_sem_chave_nao_quebra(dados, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert analise_ia.executar() is None

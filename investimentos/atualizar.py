"""
Pipeline diário: baixa fundamentos (B3 e EUA), macro (BCB), cotações, roda
as estratégias e salva tudo em investimentos/data/.

Uso:
    python -m investimentos.atualizar            # atualização completa
    python -m investimentos.atualizar --sem-us   # só Brasil (mais rápido)
    python -m investimentos.atualizar --sem-setores

Cada etapa falha de forma independente: se uma fonte estiver fora do ar, o
arquivo anterior é mantido e o status fica registrado em
data/ultima_atualizacao.json.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from datetime import datetime

import pandas as pd

from investimentos import config, estrategias
from investimentos.carteira import carregar_carteira
from investimentos.fontes import bcb, fundamentus, yahoo
from investimentos.fontes.comum import completar_colunas

log = logging.getLogger("investimentos")

ARQ_FUNDAMENTOS = config.PASTA_DADOS / "fundamentos.csv"
ARQ_RANKING = config.PASTA_DADOS / "ranking.csv"
ARQ_MACRO = config.PASTA_DADOS / "macro.json"
ARQ_COTACOES = config.PASTA_DADOS / "cotacoes.csv"
ARQ_STATUS = config.PASTA_DADOS / "ultima_atualizacao.json"

COLUNAS_HISTORICO = [
    "ticker", "pais", "preco", "pl", "pvp", "dy", "ev_ebit", "roic", "roe",
    "pontuacao_geral", "qtd_estrategias_aprovado", "estrategias_aprovado",
    "posicao_magica", "margem_seguranca_graham", "desconto_preco_teto", "earnings_yield",
]


class _ColetorAvisos(logging.Handler):
    """Guarda os avisos/erros da execução para gravar em ultima_atualizacao.json."""

    def __init__(self, maximo: int = 60):
        super().__init__(level=logging.WARNING)
        self.mensagens: list[str] = []
        self.maximo = maximo

    def emit(self, registro: logging.LogRecord) -> None:
        if len(self.mensagens) < self.maximo:
            self.mensagens.append(f"{registro.levelname} {registro.name}: {registro.getMessage()}"[:500])


def _sem_nan(objeto):
    """Troca NaN por None para o JSON ficar válido em qualquer leitor."""
    if isinstance(objeto, dict):
        return {k: _sem_nan(v) for k, v in objeto.items()}
    if isinstance(objeto, list):
        return [_sem_nan(v) for v in objeto]
    if isinstance(objeto, float) and math.isnan(objeto):
        return None
    return objeto


def _carregar_csv_anterior(caminho) -> pd.DataFrame:
    if caminho.exists():
        return pd.read_csv(caminho)
    return pd.DataFrame()


def etapa(nome: str, status: dict, funcao, *args, **kwargs):
    """Executa uma etapa registrando sucesso/erro sem derrubar o pipeline."""
    try:
        resultado = funcao(*args, **kwargs)
        status[nome] = {"ok": True, "erro": None}
        return resultado
    except Exception as erro:  # noqa: BLE001
        log.exception("Etapa '%s' falhou", nome)
        status[nome] = {"ok": False, "erro": f"{type(erro).__name__}: {erro}"}
        return None


def obter_fundamentos(status: dict, incluir_us: bool) -> pd.DataFrame:
    anterior = _carregar_csv_anterior(ARQ_FUNDAMENTOS)
    anterior = completar_colunas(anterior) if not anterior.empty else anterior

    br = etapa("fundamentus", status, fundamentus.obter_fundamentos_br)
    if br is None and not anterior.empty:
        br = anterior[anterior["pais"] == "BR"].copy()
        log.warning("Usando fundamentos BR da atualização anterior.")

    us = None
    if incluir_us:
        us = etapa("yahoo_us", status, yahoo.obter_fundamentos_us)
    if us is None and not anterior.empty:
        us = anterior[anterior["pais"] == "US"].copy()
        if incluir_us:
            log.warning("Usando fundamentos US da atualização anterior.")

    partes = [p for p in (br, us) if p is not None and not p.empty]
    if not partes:
        raise RuntimeError("Nenhuma fonte de fundamentos disponível (nem anterior).")
    return completar_colunas(pd.concat(partes, ignore_index=True))


def enriquecer_setores(df: pd.DataFrame, status: dict, carteira: pd.DataFrame) -> pd.DataFrame:
    """Busca setor/nome no Fundamentus só para os papéis relevantes e marca os setores perenes (Barsi)."""
    br = df[df["pais"] == "BR"].copy()
    if br.empty:
        return df
    previa = estrategias.consolidar(estrategias.filtrar_liquidez(br))
    candidatos = previa.head(150)["ticker"].tolist()
    candidatos += previa[previa["qtd_estrategias_aprovado"] > 0]["ticker"].tolist()
    candidatos += carteira["ticker"].tolist()
    existentes = set(br["ticker"])
    candidatos = [t for t in dict.fromkeys(candidatos) if t in existentes]  # FIIs e ações US não estão no Fundamentus
    setores = etapa("setores_br", status, fundamentus.obter_setores_br, candidatos)
    if setores is None:
        setores = fundamentus.carregar_cache_setores()
    if setores.empty:
        return df
    setores = setores.drop_duplicates(subset="ticker").set_index("ticker")
    df = df.copy()
    mascara = df["pais"] == "BR"
    df.loc[mascara, "nome"] = df.loc[mascara, "ticker"].map(setores["nome"]).where(lambda s: s.notna(), df.loc[mascara, "nome"])
    df.loc[mascara, "setor"] = df.loc[mascara, "ticker"].map(setores["setor"]).where(lambda s: s.notna(), df.loc[mascara, "setor"])
    sub = df.loc[mascara, "ticker"].map(setores["subsetor"]) if "subsetor" in setores.columns else pd.Series(index=df.index[mascara], dtype=object)
    df["setor_barsi"] = None
    df.loc[mascara, "setor_barsi"] = [fundamentus.classificar_setor_barsi(s, ss) for s, ss in zip(df.loc[mascara, "setor"], sub)]
    return df


def obter_macro(status: dict) -> dict:
    anterior = json.loads(ARQ_MACRO.read_text(encoding="utf-8")) if ARQ_MACRO.exists() else {}
    macro = etapa("bcb", status, bcb.obter_macro) or dict(anterior)
    def _vazio(v):
        return v is None or (isinstance(v, float) and math.isnan(v))

    if _vazio(macro.get("dolar")):
        dolar = etapa("dolar_yahoo", status, yahoo.obter_dolar)
        if dolar is not None and not math.isnan(dolar):
            macro["dolar"] = dolar
            macro["fonte_dolar"] = "Yahoo BRL=X"
    # mantém valores antigos quando o novo veio vazio
    for chave, valor in anterior.items():
        if chave == "erros":
            continue
        if _vazio(macro.get(chave)) and not _vazio(valor):
            macro[chave] = valor
    # juro real depende de Selic/CDI e IPCA, que podem ter vindo do arquivo anterior
    macro["juro_real_selic"] = bcb.juro_real(float(macro.get("selic_meta") or math.nan), float(macro.get("ipca_12m") or math.nan))
    macro["juro_real_cdi"] = bcb.juro_real(float(macro.get("cdi_12m") or math.nan), float(macro.get("ipca_12m") or math.nan))
    macro["atualizado_em"] = datetime.now().isoformat(timespec="seconds")
    return macro


def obter_cotacoes(status: dict, carteira: pd.DataFrame, fundamentos: pd.DataFrame) -> pd.DataFrame:
    """Cotações de ETFs e dos ativos da carteira que não estão nos fundamentos."""
    conhecidos = set(fundamentos["ticker"])
    pedidos = {}
    for t in list(config.ETFS_US):
        pedidos[t] = "US"
    for t in list(config.ETFS_BR):
        pedidos[t] = "BR"
    for _, linha in carteira.iterrows():
        if linha["ticker"] and linha["ticker"] not in conhecidos and pd.isna(linha.get("valor_atual")):
            pedidos[linha["ticker"]] = "US" if linha["moeda"] == "USD" else "BR"
    mapa = {t: yahoo.ticker_yahoo(t, pais) for t, pais in pedidos.items()}
    cot = etapa("cotacoes_yahoo", status, yahoo.obter_cotacoes, list(mapa.values()))
    if cot is None:
        return _carregar_csv_anterior(ARQ_COTACOES)
    inverso = {v: k for k, v in mapa.items()}
    cot["ticker"] = cot["ticker_yahoo"].map(inverso)
    cot["descricao"] = cot["ticker"].map({**config.ETFS_US, **config.ETFS_BR})
    return cot[["ticker", "ticker_yahoo", "preco", "data", "descricao"]]


def salvar_historico(ranking: pd.DataFrame) -> None:
    config.PASTA_HISTORICO.mkdir(parents=True, exist_ok=True)
    hoje = datetime.now().strftime("%Y-%m-%d")
    colunas = [c for c in COLUNAS_HISTORICO if c in ranking.columns]
    ranking[colunas].round(4).to_csv(config.PASTA_HISTORICO / f"ranking_{hoje}.csv", index=False)


def executar(incluir_us: bool = True, incluir_setores: bool = True) -> dict:
    config.PASTA_DADOS.mkdir(parents=True, exist_ok=True)
    status: dict = {}
    inicio = datetime.now()
    coletor = _ColetorAvisos()
    logging.getLogger().addHandler(coletor)
    carteira = carregar_carteira()

    fundamentos = obter_fundamentos(status, incluir_us)
    if incluir_setores:
        fundamentos = enriquecer_setores(fundamentos, status, carteira)
    fundamentos.to_csv(ARQ_FUNDAMENTOS, index=False)

    macro = obter_macro(status)
    ARQ_MACRO.write_text(json.dumps(_sem_nan(macro), ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    taxa_minima = estrategias.taxa_minima_atratividade(
        float(macro.get("ipca_12m") or math.nan), selic=float(macro.get("selic_meta") or math.nan)
    )
    ranking = estrategias.consolidar(estrategias.filtrar_liquidez(fundamentos), taxa_minima=taxa_minima)
    ranking.to_csv(ARQ_RANKING, index=False)
    salvar_historico(ranking)

    cotacoes = obter_cotacoes(status, carteira, fundamentos)
    cotacoes.to_csv(ARQ_COTACOES, index=False)

    status_final = {
        "atualizado_em": datetime.now().isoformat(timespec="seconds"),
        "duracao_segundos": round((datetime.now() - inicio).total_seconds(), 1),
        "papeis_br": int((fundamentos["pais"] == "BR").sum()),
        "papeis_us": int((fundamentos["pais"] == "US").sum()),
        "taxa_minima_atratividade": None if math.isnan(taxa_minima) else round(taxa_minima, 4),
        "setores_br_em_cache": int(len(fundamentus.carregar_cache_setores())),
        "etapas": status,
        "avisos": coletor.mensagens,
    }
    logging.getLogger().removeHandler(coletor)
    ARQ_STATUS.write_text(json.dumps(_sem_nan(status_final), ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Atualização concluída em %.0fs. Status: %s", status_final["duracao_segundos"], {k: v["ok"] for k, v in status.items()})
    return status_final


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Atualiza os dados da ferramenta de investimentos.")
    parser.add_argument("--sem-us", action="store_true", help="não baixa fundamentos das ações americanas")
    parser.add_argument("--sem-setores", action="store_true", help="não consulta setor por papel no Fundamentus")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    status = executar(incluir_us=not args.sem_us, incluir_setores=not args.sem_setores)
    falhas = [k for k, v in status["etapas"].items() if not v["ok"]]
    if falhas:
        log.warning("Etapas com falha: %s", ", ".join(falhas))
    return 0


if __name__ == "__main__":
    sys.exit(main())

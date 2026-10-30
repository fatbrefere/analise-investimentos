"""
Carteira do investidor: valorização, diversificação por tipo e por moeda, e
sugestão de direcionamento dos próximos aportes.

O arquivo carteira.csv tem as colunas:
    ticker, tipo, moeda, quantidade, preco_medio, valor_atual, descricao

- ticker: código do ativo (PETR4, AAPL, VOO, MXRF11). Pode ficar vazio para
  renda fixa e caixa.
- tipo: um de config.TIPOS_DE_ATIVO.
- moeda: BRL ou USD.
- quantidade e preco_medio: na moeda do ativo.
- valor_atual: opcional. Se preenchido, é usado como valor de mercado (útil
  para renda fixa, caixa e cripto). Se vazio, usa quantidade x cotação.
"""
from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

from investimentos import config

COLUNAS_CARTEIRA = ["ticker", "tipo", "moeda", "quantidade", "preco_medio", "valor_atual", "descricao"]


def carregar_carteira(caminho: Path | None = None) -> pd.DataFrame:
    """Lê carteira.csv, ou a variável de ambiente CARTEIRA_CSV, ou o exemplo.

    CARTEIRA_CSV permite usar a carteira pessoal no GitHub Actions (como secret)
    sem colocá-la no repositório.
    """
    import os
    from io import StringIO

    texto_env = os.environ.get("CARTEIRA_CSV", "").strip()
    if caminho is None and texto_env:
        return normalizar_carteira(pd.read_csv(StringIO(texto_env), dtype={"ticker": str, "tipo": str, "moeda": str, "descricao": str}))
    caminho = caminho or config.ARQUIVO_CARTEIRA
    if not Path(caminho).exists():
        caminho = config.ARQUIVO_CARTEIRA_EXEMPLO
    df = pd.read_csv(caminho, dtype={"ticker": str, "tipo": str, "moeda": str, "descricao": str})
    return normalizar_carteira(df)


def normalizar_carteira(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for coluna in COLUNAS_CARTEIRA:
        if coluna not in df.columns:
            df[coluna] = pd.NA
    df = df[COLUNAS_CARTEIRA]
    df["ticker"] = df["ticker"].fillna("").astype(str).str.strip().str.upper()
    df["tipo"] = df["tipo"].astype(str).str.strip()
    df["moeda"] = df["moeda"].fillna("BRL").astype(str).str.strip().str.upper()
    for coluna in ("quantidade", "preco_medio", "valor_atual"):
        df[coluna] = pd.to_numeric(df[coluna], errors="coerce")
    desconhecidos = sorted(set(df["tipo"]) - set(config.TIPOS_DE_ATIVO))
    if desconhecidos:
        raise ValueError(f"Tipos de ativo desconhecidos na carteira: {desconhecidos}. Use um de {config.TIPOS_DE_ATIVO}.")
    return df.reset_index(drop=True)


def avaliar_carteira(carteira: pd.DataFrame, precos: dict[str, float], dolar: float) -> pd.DataFrame:
    """Calcula valor de mercado, custo e resultado de cada posição, em moeda local e em R$."""
    df = carteira.copy()
    df["preco_atual"] = df["ticker"].map(lambda t: precos.get(t, math.nan))
    custo = df["quantidade"] * df["preco_medio"]
    valor_cotacao = df["quantidade"] * df["preco_atual"]
    df["valor"] = df["valor_atual"].where(df["valor_atual"].notna(), valor_cotacao)
    # sem cotação e sem valor informado: assume o custo para não sumir da alocação
    df["valor"] = df["valor"].where(df["valor"].notna(), custo)
    df["custo"] = custo
    df["resultado"] = df["valor"] - df["custo"]
    df["resultado_pct"] = df["resultado"] / df["custo"]
    fator = df["moeda"].map(lambda m: dolar if m == "USD" else 1.0)
    if math.isnan(dolar):
        fator = fator.where(df["moeda"] != "USD", math.nan)
    df["valor_brl"] = df["valor"] * fator
    df["custo_brl"] = df["custo"] * fator
    df["sem_cotacao"] = df["preco_atual"].isna() & df["valor_atual"].isna() & (df["ticker"] != "")
    return df


def alocacao(df_avaliada: pd.DataFrame, por: str, alvo: dict[str, float]) -> pd.DataFrame:
    """Compara alocação atual (em R$) com a alvo, por 'tipo' ou 'moeda'."""
    total = df_avaliada["valor_brl"].sum()
    atual = df_avaliada.groupby(por)["valor_brl"].sum()
    categorias = list(dict.fromkeys(list(alvo.keys()) + list(atual.index)))
    linhas = []
    for categoria in categorias:
        valor = float(atual.get(categoria, 0.0))
        pct_atual = valor / total if total else 0.0
        pct_alvo = float(alvo.get(categoria, 0.0))
        linhas.append({
            por: categoria,
            "valor_brl": valor,
            "pct_atual": pct_atual,
            "pct_alvo": pct_alvo,
            "diferenca_pp": pct_atual - pct_alvo,
            "valor_para_alvo": pct_alvo * total - valor,
        })
    return pd.DataFrame(linhas).sort_values("pct_alvo", ascending=False).reset_index(drop=True)


def sugerir_aporte(df_avaliada: pd.DataFrame, valor_aporte: float, alvo: dict[str, float], por: str = "tipo") -> pd.DataFrame:
    """Distribui um novo aporte priorizando as categorias abaixo do alvo (sem vender nada)."""
    total = df_avaliada["valor_brl"].sum()
    atual = df_avaliada.groupby(por)["valor_brl"].sum()
    total_futuro = total + valor_aporte
    deficits = {}
    for categoria, pct in alvo.items():
        if pct <= 0:
            continue
        deficit = pct * total_futuro - float(atual.get(categoria, 0.0))
        if deficit > 0:
            deficits[categoria] = deficit
    soma = sum(deficits.values())
    linhas = []
    if soma <= 0:
        # já está no alvo: distribui proporcionalmente ao alvo
        for categoria, pct in alvo.items():
            if pct > 0:
                linhas.append({por: categoria, "aporte_sugerido": valor_aporte * pct})
    else:
        for categoria, deficit in deficits.items():
            linhas.append({por: categoria, "aporte_sugerido": valor_aporte * deficit / soma})
    df = pd.DataFrame(linhas, columns=[por, "aporte_sugerido"])
    return df.sort_values("aporte_sugerido", ascending=False).reset_index(drop=True)


def resumo(df_avaliada: pd.DataFrame) -> dict:
    valor = float(df_avaliada["valor_brl"].sum())
    custo = float(df_avaliada["custo_brl"].sum())
    return {
        "valor_brl": valor,
        "custo_brl": custo,
        "resultado_brl": valor - custo,
        "resultado_pct": (valor / custo - 1) if custo else math.nan,
        "posicoes": int(len(df_avaliada)),
        "sem_cotacao": int(df_avaliada["sem_cotacao"].sum()),
    }

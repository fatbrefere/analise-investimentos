"""
Fonte de dados para ações brasileiras: Fundamentus (https://www.fundamentus.com.br).

A página "resultado.php" lista todas as ações da B3 com os principais
indicadores fundamentalistas em uma única tabela HTML. É a fonte gratuita
mais usada no Brasil para aplicar Fórmula Mágica, Graham e Bazin.
"""
from __future__ import annotations

import io
import logging
import time
from pathlib import Path

import pandas as pd
import requests

from investimentos import config
from investimentos.fontes.comum import completar_colunas, derivar_por_acao, numero_br

log = logging.getLogger(__name__)

URL_RESULTADO = "https://www.fundamentus.com.br/resultado.php"
URL_DETALHES = "https://www.fundamentus.com.br/detalhes.php?papel={ticker}"

# Mapeamento das colunas do Fundamentus para o esquema comum
MAPA_COLUNAS = {
    "Papel": "ticker",
    "Cotação": "preco",
    "P/L": "pl",
    "P/VP": "pvp",
    "Div.Yield": "dy",
    "EV/EBIT": "ev_ebit",
    "EV/EBITDA": "ev_ebitda",
    "Mrg Ebit": "margem_ebit",
    "Mrg. Líq.": "margem_liquida",
    "Liq. Corr.": "liquidez_corrente",
    "ROIC": "roic",
    "ROE": "roe",
    "Liq.2meses": "liquidez",
    "Patrim. Líq": "patrimonio_liquido",
    "Dív.Brut/ Patrim.": "divida_patrimonio",
    "Cresc. Rec.5a": "cresc_receita_5a",
}


def baixar_html(url: str = URL_RESULTADO) -> str:
    resposta = requests.get(url, headers=config.HTTP_HEADERS, timeout=config.HTTP_TIMEOUT)
    resposta.raise_for_status()
    resposta.encoding = resposta.apparent_encoding or "latin-1"
    return resposta.text


def _normalizar_nome_coluna(nome: str) -> str:
    return " ".join(str(nome).split())


def _tabela_para_strings(html: str) -> pd.DataFrame:
    """Lê a tabela de resultados como texto puro (sem conversão numérica automática).

    O pandas.read_html tenta adivinhar números e erra com o formato brasileiro
    ("1.234,56"), então os valores são extraídos célula a célula com lxml e
    convertidos depois por numero_br().
    """
    import lxml.html

    arvore = lxml.html.fromstring(html)
    for tabela in arvore.xpath("//table"):
        cabecalho = [_normalizar_nome_coluna(th.text_content()) for th in tabela.xpath(".//thead//th | .//tr[1]/th")]
        if "Papel" not in cabecalho:
            continue
        linhas = []
        for tr in tabela.xpath(".//tbody/tr | .//tr[td]"):
            celulas = [td.text_content().strip() for td in tr.xpath("./td")]
            if len(celulas) == len(cabecalho):
                linhas.append(celulas)
        return pd.DataFrame(linhas, columns=cabecalho)
    raise ValueError("Tabela de resultados do Fundamentus não encontrada no HTML.")


def parse_resultado(html: str) -> pd.DataFrame:
    """Converte o HTML da página resultado.php no esquema comum."""
    tabela = _tabela_para_strings(html)

    mapa = {_normalizar_nome_coluna(k): v for k, v in MAPA_COLUNAS.items()}
    df = tabela.rename(columns=mapa)
    df = df[[c for c in df.columns if c in MAPA_COLUNAS.values()]].copy()

    for coluna in df.columns:
        if coluna == "ticker":
            continue
        df[coluna] = df[coluna].map(numero_br)

    df["ticker"] = df["ticker"].astype(str).str.strip().str.upper()
    df["pais"] = "BR"
    df["moeda"] = "BRL"
    df = completar_colunas(df)
    df = derivar_por_acao(df)
    df = df.drop_duplicates(subset="ticker").reset_index(drop=True)
    return df


def obter_fundamentos_br() -> pd.DataFrame:
    """Baixa e normaliza os fundamentos de todas as ações da B3."""
    log.info("Baixando fundamentos da B3 (Fundamentus)...")
    html = baixar_html()
    df = parse_resultado(html)
    log.info("Fundamentus: %d papéis carregados.", len(df))
    return df


# ---------------------------------------------------------------------------
# Setor por papel (página de detalhes). Só é consultado para os papéis que
# chegam às listas finais e fica em cache em disco, porque são ~900 páginas.
# ---------------------------------------------------------------------------
ARQUIVO_CACHE_SETORES = config.PASTA_DADOS / "setores_br.csv"


def parse_detalhes(html: str) -> dict:
    """Extrai nome, setor e subsetor da página detalhes.php."""
    resultado = {"nome": None, "setor": None, "subsetor": None}
    try:
        tabelas = pd.read_html(io.StringIO(html))
    except ValueError:
        return resultado
    for t in tabelas:
        valores = t.astype(str).values.tolist()
        for linha in valores:
            for i, celula in enumerate(linha):
                rotulo = celula.replace("?", "").strip()
                if i + 1 >= len(linha):
                    continue
                if rotulo == "Empresa":
                    resultado["nome"] = linha[i + 1].strip()
                elif rotulo == "Setor":
                    resultado["setor"] = linha[i + 1].strip()
                elif rotulo == "Subsetor":
                    resultado["subsetor"] = linha[i + 1].strip()
    return resultado


def carregar_cache_setores(caminho: Path | None = None) -> pd.DataFrame:
    caminho = caminho or ARQUIVO_CACHE_SETORES
    if caminho.exists():
        return pd.read_csv(caminho, dtype=str)
    return pd.DataFrame(columns=["ticker", "nome", "setor", "subsetor"])


def obter_setores_br(tickers: list[str], caminho: Path | None = None, maximo_novos: int = 150) -> pd.DataFrame:
    """Retorna nome/setor dos tickers pedidos, consultando o site só para os que não estão em cache."""
    caminho = caminho or ARQUIVO_CACHE_SETORES
    cache = carregar_cache_setores(caminho)
    conhecidos = set(cache["ticker"].astype(str))
    faltantes = [t for t in dict.fromkeys(tickers) if t not in conhecidos][:maximo_novos]
    novos = []
    falhas = 0
    for i, ticker in enumerate(faltantes):
        if i:
            time.sleep(config.PAUSA_ENTRE_REQUISICOES)
        try:
            html = baixar_html(URL_DETALHES.format(ticker=ticker))
            dados = parse_detalhes(html)
            if not any(dados.values()):
                raise ValueError("página sem Empresa/Setor (layout mudou ou bloqueio)")
            novos.append({"ticker": ticker, **{k: dados.get(k) for k in ("nome", "setor", "subsetor")}})
        except Exception as erro:  # noqa: BLE001 - não interromper a atualização por um papel
            falhas += 1
            log.warning("Falha ao buscar setor de %s: %s", ticker, erro)
            if falhas >= 5 and not novos:
                raise RuntimeError(f"{falhas} falhas seguidas ao consultar detalhes no Fundamentus; última: {erro}") from erro
    log.info("Setores Fundamentus: %d novos, %d falhas, %d em cache.", len(novos), falhas, len(conhecidos))
    if novos:
        cache = pd.concat([cache, pd.DataFrame(novos)], ignore_index=True)
        cache = cache.drop_duplicates(subset="ticker")
        caminho.parent.mkdir(parents=True, exist_ok=True)
        cache.to_csv(caminho, index=False)
    return cache


def classificar_setor_barsi(setor: str | None, subsetor: str | None = None) -> str | None:
    """Mapeia o setor do Fundamentus para os setores perenes de Barsi (BESST)."""
    texto = f"{setor or ''} {subsetor or ''}".lower()
    if "banc" in texto or "intermediários financeiros" in texto:
        return "Bancos"
    if "energia" in texto or "elétric" in texto:
        return "Energia"
    if "água" in texto or "saneamento" in texto:
        return "Saneamento"
    if "segur" in texto or "previdência" in texto:
        return "Seguros"
    if "telecom" in texto:
        return "Telecom"
    return None

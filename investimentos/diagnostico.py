"""
Diagnóstico do ambiente: testa bibliotecas e o acesso a cada site de dados.

Uso:  python -m investimentos.diagnostico            # mostra o relatório
      python -m investimentos.diagnostico --enviar   # e envia ao GitHub (branch diagnostico-local)
"""
from __future__ import annotations

import importlib
import io
import json
import os
import platform
import sys
from contextlib import redirect_stdout

from investimentos import config

ARQUIVO_RELATORIO = config.PASTA_DADOS / "diagnostico_local.txt"

SITES = {
    "Fundamentus (ações B3)": "https://www.fundamentus.com.br/resultado.php",
    "Fundamentus (detalhes)": "https://www.fundamentus.com.br/detalhes.php?papel=PETR4",
    "Banco Central (SGS)": "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/1?formato=json",
    "Banco Central (Focus)": config.URL_FOCUS_IPCA_12M,
    "Yahoo Finance": "https://query2.finance.yahoo.com/v8/finance/chart/PETR4.SA?range=5d&interval=1d",
}


def executar() -> tuple[str, int]:
    """Roda todos os testes e devolve (relatório em texto, número de problemas)."""
    saida = io.StringIO()
    with redirect_stdout(saida):
        problemas = _rodar()
    return saida.getvalue(), problemas


def _rodar() -> int:
    print(f"Python {sys.version.split()[0]} em {sys.executable}")
    print(f"Sistema: {platform.platform()}")
    proxies = {k: v for k, v in os.environ.items() if k.upper() in ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "REQUESTS_CA_BUNDLE", "SSL_CERT_FILE")}
    print(f"Variáveis de proxy/certificado: {proxies or 'nenhuma'}")
    try:
        import certifi
        print(f"Certificados (certifi): {certifi.where()}")
    except Exception as erro:  # noqa: BLE001
        print(f"certifi indisponível: {erro}")
    print("\n== Git ==")
    try:
        from investimentos import git_util

        print(f"  commit local: {git_util._git('log', '-1', '--format=%h %s')}")
        try:
            git_util._git("fetch", "origin", "main")
            print(f"  commit GitHub: {git_util._git('log', '-1', '--format=%h %s', 'origin/main')}")
            diff = git_util._git("diff", "--stat", "origin/main")
            print("  diferenças em relação ao GitHub: " + (("\n    " + diff.replace("\n", "\n    ")) if diff else "nenhuma"))
        except Exception as erro:  # noqa: BLE001
            print(f"  não foi possível comparar com o GitHub: {erro}")
        alterados = git_util._git("status", "--short")
        print("  arquivos alterados localmente: " + (("\n    " + alterados.replace("\n", "\n    ")) if alterados else "nenhum"))
    except Exception as erro:  # noqa: BLE001
        print(f"  git indisponível: {erro}")
    try:
        from investimentos.fontes import bcb as _bcb

        print(f"  bcb.py em uso: {_bcb.__file__} | tem juro_real: {hasattr(_bcb, 'juro_real')}")
    except Exception as erro:  # noqa: BLE001
        print(f"  erro ao importar bcb: {erro}")

    status = config.PASTA_DADOS / "ultima_atualizacao.json"
    if status.exists():
        try:
            dados = json.loads(status.read_text(encoding="utf-8"))
            print(f"\n== Última atualização local ({dados.get('atualizado_em')}) ==")
            for nome, etapa in dados.get("etapas", {}).items():
                print(f"  {'OK  ' if etapa.get('ok') else 'ERRO'} {nome}: {etapa.get('erro') or ''}")
            for aviso in dados.get("avisos", [])[:15]:
                print(f"  aviso: {aviso[:300]}")
        except Exception as erro:  # noqa: BLE001
            print(f"  não foi possível ler {status}: {erro}")
    print("\n== Bibliotecas ==")
    problemas = 0
    for modulo in ("pandas", "numpy", "requests", "lxml", "yfinance", "streamlit", "plotly", "xlsxwriter", "openpyxl"):
        try:
            m = importlib.import_module(modulo)
            print(f"  OK   {modulo} {getattr(m, '__version__', '')}")
        except Exception as erro:  # noqa: BLE001
            problemas += 1
            print(f"  FALTA {modulo}: {type(erro).__name__}: {erro}")

    print("\n== Sites ==")
    import requests

    for nome, url in SITES.items():
        try:
            r = requests.get(url, headers=config.HTTP_HEADERS, timeout=config.HTTP_TIMEOUT)
            print(f"  {'OK  ' if r.ok else 'ERRO'} {nome}: HTTP {r.status_code}, {len(r.content)} bytes")
            if not r.ok:
                problemas += 1
        except Exception as erro:  # noqa: BLE001
            problemas += 1
            print(f"  ERRO {nome}: {type(erro).__name__}: {erro}")

    print("\n== yfinance ==")
    try:
        import yfinance as yf

        preco = yf.Ticker("PETR4.SA").history(period="5d")["Close"].dropna()
        print(f"  OK   PETR4.SA último fechamento: {float(preco.iloc[-1]):.2f}" if not preco.empty else "  ERRO sem dados para PETR4.SA")
    except Exception as erro:  # noqa: BLE001
        problemas += 1
        print(f"  ERRO yfinance: {type(erro).__name__}: {erro}")

    print("\n== Parser Fundamentus ==")
    try:
        from investimentos.fontes import fundamentus

        df = fundamentus.obter_fundamentos_br()
        print(f"  OK   {len(df)} papéis lidos")
    except Exception as erro:  # noqa: BLE001
        problemas += 1
        print(f"  ERRO {type(erro).__name__}: {erro}")

    print(f"\nResultado: {'tudo OK' if problemas == 0 else f'{problemas} problema(s) encontrado(s)'}")
    return problemas


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Diagnóstico do ambiente da ferramenta de investimentos.")
    parser.add_argument("--enviar", action="store_true", help="envia o relatório ao GitHub no branch diagnostico-local")
    args = parser.parse_args(argv)
    relatorio, problemas = executar()
    print(relatorio)
    config.PASTA_DADOS.mkdir(parents=True, exist_ok=True)
    ARQUIVO_RELATORIO.write_text(relatorio, encoding="utf-8")
    print(f"Relatório salvo em {ARQUIVO_RELATORIO}")
    if args.enviar:
        from investimentos import git_util

        arquivos = {"diagnostico/diagnostico_local.txt": ARQUIVO_RELATORIO}
        status = config.PASTA_DADOS / "ultima_atualizacao.json"
        if status.exists():
            arquivos["diagnostico/ultima_atualizacao_local.json"] = status
        commit = git_util.enviar_arquivos_para_branch(arquivos, "Diagnóstico local (linha de comando)")
        print(f"Relatório enviado ao GitHub: branch {git_util.BRANCH_DIAGNOSTICO}, commit {commit[:7]}")
    return 0 if problemas == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

"""
Diagnóstico do ambiente: testa bibliotecas e o acesso a cada site de dados.

Uso:  python -m investimentos.diagnostico
Cole a saída na conversa para identificar o que está falhando.
"""
from __future__ import annotations

import importlib
import platform
import sys

from investimentos import config

SITES = {
    "Fundamentus (ações B3)": "https://www.fundamentus.com.br/resultado.php",
    "Fundamentus (detalhes)": "https://www.fundamentus.com.br/detalhes.php?papel=PETR4",
    "Banco Central (SGS)": "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/1?formato=json",
    "Banco Central (Focus)": config.URL_FOCUS_IPCA_12M,
    "Yahoo Finance": "https://query2.finance.yahoo.com/v8/finance/chart/PETR4.SA?range=5d&interval=1d",
}


def main() -> int:
    print(f"Python {sys.version.split()[0]} em {sys.executable}")
    print(f"Sistema: {platform.platform()}")
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
    return 0 if problemas == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

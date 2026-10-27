"""
Parâmetros da ferramenta de investimentos.

Tudo que é "regra de bolso" das estratégias fica aqui, para você ajustar
sem mexer no código das estratégias.
"""
from pathlib import Path

PASTA_BASE = Path(__file__).resolve().parent
PASTA_DADOS = PASTA_BASE / "data"
PASTA_HISTORICO = PASTA_DADOS / "historico"
ARQUIVO_CARTEIRA = PASTA_BASE / "carteira.csv"
ARQUIVO_CARTEIRA_EXEMPLO = PASTA_BASE / "carteira_exemplo.csv"

# ---------------------------------------------------------------------------
# Filtros gerais (aplicados antes de qualquer estratégia)
# ---------------------------------------------------------------------------
# Volume médio diário mínimo (R$, média dos últimos 2 meses, coluna
# "Liq.2meses" do Fundamentus) para ações brasileiras. Evita papéis
# ilíquidos que aparecem "baratos" só porque ninguém negocia.
LIQUIDEZ_MINIMA_BR = 1_000_000.0
# Volume médio diário mínimo (US$) para ações americanas.
# Pausa entre consultas de setor no Fundamentus (segundos), para não ser bloqueado.
PAUSA_ENTRE_REQUISICOES = 0.5
VOLUME_MINIMO_US = 1_000_000.0

# ---------------------------------------------------------------------------
# Fórmula Mágica (Joel Greenblatt - "A Fórmula Mágica para Bater o Mercado")
# ---------------------------------------------------------------------------
# Ranking combinado de EV/EBIT (quanto menor, mais barata) e ROIC (quanto
# maior, melhor a empresa). Quantas ações compõem a lista final.
MAGICA_TOP_N = 30
MAGICA_EV_EBIT_MINIMO = 0.0   # ignora EV/EBIT negativo (prejuízo operacional)
MAGICA_ROIC_MINIMO = 0.0

# ---------------------------------------------------------------------------
# Benjamin Graham ("O Investidor Inteligente")
# ---------------------------------------------------------------------------
GRAHAM_PL_MAXIMO = 15.0
GRAHAM_PVP_MAXIMO = 1.5
GRAHAM_PL_X_PVP_MAXIMO = 22.5
GRAHAM_LIQUIDEZ_CORRENTE_MINIMA = 1.5
GRAHAM_DIVIDA_PATRIMONIO_MAXIMA = 1.0
GRAHAM_MARGEM_SEGURANCA_MINIMA = 0.20   # 20% abaixo do preço justo

# ---------------------------------------------------------------------------
# Dividendos - Décio Bazin ("Faça Fortuna com Ações") e Luiz Barsi
# ("O Rei dos Dividendos")
# ---------------------------------------------------------------------------
# Bazin: só compra se o dividend yield for >= 6% a.a.; preço teto =
# dividendos por ação / 6%. Barsi acrescenta foco em setores perenes
# (bancos, energia, saneamento, seguros, telecom) e dívida controlada.
BAZIN_DY_MINIMO = 0.06
BAZIN_DIVIDA_PATRIMONIO_MAXIMA = 1.0
BAZIN_DESCONTO_MINIMO_PRECO_TETO = 0.0   # preço atual <= preço teto
BARSI_SETORES_PERENES = ["Bancos", "Energia", "Saneamento", "Seguros", "Telecom"]

# ---------------------------------------------------------------------------
# Warren Buffett (qualidade: empresa boa a preço razoável)
# ---------------------------------------------------------------------------
BUFFETT_ROE_MINIMO = 0.15
BUFFETT_MARGEM_LIQUIDA_MINIMA = 0.10
BUFFETT_DIVIDA_PATRIMONIO_MAXIMA = 0.50
BUFFETT_CRESCIMENTO_RECEITA_MINIMO = 0.0  # crescimento de receita 5 anos > 0
BUFFETT_PL_MAXIMO = 20.0
BUFFETT_PVP_MAXIMO = 3.0

# ---------------------------------------------------------------------------
# Taxa mínima de atratividade: a carteira precisa ganhar da inflação.
# Earnings yield (1 / P/L) de uma ação deve superar IPCA + prêmio de risco.
# ---------------------------------------------------------------------------
PREMIO_DE_RISCO_SOBRE_IPCA = 0.05   # 5 pontos percentuais acima do IPCA

# ---------------------------------------------------------------------------
# Universo de ações e ETFs americanos acompanhados via Yahoo Finance.
# Não existe um "screener" gratuito completo para os EUA, então aqui vai
# uma lista editável de grandes empresas + ETFs amplos para diversificação.
# ---------------------------------------------------------------------------
TICKERS_US = [
    # Tecnologia
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "AVGO", "ORCL", "CSCO", "ADBE",
    "INTC", "AMD", "QCOM", "TXN", "IBM", "CRM",
    # Saúde
    "JNJ", "PFE", "MRK", "ABBV", "LLY", "UNH", "CVS", "AMGN", "BMY", "TMO",
    # Financeiro
    "JPM", "BAC", "WFC", "GS", "MS", "V", "MA", "AXP", "BRK-B", "C",
    # Consumo
    "PG", "KO", "PEP", "WMT", "COST", "MCD", "NKE", "HD", "LOW", "SBUX", "TGT",
    "PM", "MO", "CL", "KMB", "GIS",
    # Industrial / Energia / Materiais / Telecom / Utilities
    "XOM", "CVX", "COP", "CAT", "DE", "HON", "UPS", "LMT", "RTX", "GE",
    "MMM", "VZ", "T", "DUK", "SO", "NEE", "LIN", "FCX", "NEM",
]

ETFS_US = {
    # ticker: descrição curta para a tela de diversificação
    "VOO": "S&P 500",
    "VTI": "Mercado total EUA",
    "VXUS": "Ações internacionais ex-EUA",
    "VNQ": "Imóveis (REITs) EUA",
    "SCHD": "Dividendos EUA",
    "BND": "Renda fixa EUA",
    "TIP": "Títulos protegidos da inflação (TIPS)",
    "GLD": "Ouro",
}

# ETFs/ativos brasileiros para referência de preço (opcional)
ETFS_BR = {
    "BOVA11": "Ibovespa",
    "IVVB11": "S&P 500 em reais",
    "HASH11": "Cripto (cesta)",
}

# ---------------------------------------------------------------------------
# Alocação alvo da carteira (soma 100%). Usada na tela de diversificação
# para sugerir onde direcionar os próximos aportes.
# ---------------------------------------------------------------------------
ALOCACAO_ALVO_TIPO = {
    "Ação BR": 0.30,
    "FII": 0.15,
    "Ação US": 0.20,
    "ETF US": 0.10,
    "Renda Fixa BR": 0.20,
    "Renda Fixa US": 0.0,
    "Cripto": 0.0,
    "Caixa": 0.05,
}
ALOCACAO_ALVO_MOEDA = {
    "BRL": 0.70,
    "USD": 0.30,
}
TIPOS_DE_ATIVO = list(ALOCACAO_ALVO_TIPO.keys())

# ---------------------------------------------------------------------------
# Séries do Banco Central (SGS) para dados macro.
# ---------------------------------------------------------------------------
SERIES_BCB = {
    "ipca_mensal": 433,     # IPCA variação mensal (%)
    "selic_meta": 432,      # Meta Selic (% a.a.)
    "cdi_diario": 12,       # CDI diário (% a.d.)
    "cdi_anual": 4389,      # CDI anualizado (% a.a.), reserva
    "dolar_ptax": 1,        # Dólar PTAX venda (R$)
}

# Cabeçalho usado nas requisições HTTP (alguns sites bloqueiam clientes sem User-Agent)
HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}
HTTP_TIMEOUT = 30

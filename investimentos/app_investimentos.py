"""
Painel Streamlit da ferramenta de investimentos.

Rodar:  streamlit run investimentos/app_investimentos.py
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
from io import BytesIO
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from investimentos import carteira as mod_carteira  # noqa: E402
from investimentos import config, estrategias  # noqa: E402
from investimentos.atualizar import ARQ_COTACOES, ARQ_FUNDAMENTOS, ARQ_MACRO, ARQ_STATUS  # noqa: E402

st.set_page_config(page_title="Análise de Ações", page_icon="📈", layout="wide")


# ---------------------------------------------------------------------------
# Carregamento de dados (com cache)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=600)
def carregar_fundamentos() -> pd.DataFrame:
    if not ARQ_FUNDAMENTOS.exists():
        return pd.DataFrame()
    df = pd.read_csv(ARQ_FUNDAMENTOS)
    if "setor_barsi" not in df.columns:
        df["setor_barsi"] = None
    return df


@st.cache_data(ttl=600)
def carregar_macro() -> dict:
    return json.loads(ARQ_MACRO.read_text(encoding="utf-8")) if ARQ_MACRO.exists() else {}


@st.cache_data(ttl=600)
def carregar_status() -> dict:
    return json.loads(ARQ_STATUS.read_text(encoding="utf-8")) if ARQ_STATUS.exists() else {}


@st.cache_data(ttl=600)
def carregar_cotacoes() -> pd.DataFrame:
    return pd.read_csv(ARQ_COTACOES) if ARQ_COTACOES.exists() else pd.DataFrame(columns=["ticker", "preco", "data", "descricao"])


@st.cache_data(ttl=600)
def carregar_historico() -> pd.DataFrame:
    arquivos = sorted(config.PASTA_HISTORICO.glob("ranking_*.csv"))
    partes = []
    for arq in arquivos:
        df = pd.read_csv(arq)
        df["data"] = arq.stem.replace("ranking_", "")
        partes.append(df)
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()


def _f(valor, casas=2, sufixo="") -> str:
    if valor is None or (isinstance(valor, float) and math.isnan(valor)):
        return "—"
    return f"{valor:,.{casas}f}{sufixo}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(valor) -> str:
    return "—" if valor is None or (isinstance(valor, float) and math.isnan(valor)) else _f(valor * 100, 1, "%")


def _moeda(valor, simbolo="R$") -> str:
    return "—" if valor is None or (isinstance(valor, float) and math.isnan(valor)) else f"{simbolo} {_f(valor, 2)}"


def tabela_formatada(df: pd.DataFrame, colunas: dict[str, str]) -> pd.DataFrame:
    """Seleciona e renomeia colunas; percentuais (fração) viram % com 1 casa."""
    presentes = {k: v for k, v in colunas.items() if k in df.columns}
    saida = df[list(presentes)].copy()
    pct = {"dy", "roic", "roe", "margem_liquida", "margem_ebit", "cresc_receita_5a", "margem_seguranca_graham", "desconto_preco_teto", "earnings_yield", "resultado_pct", "pct_atual", "pct_alvo", "diferenca_pp"}
    for coluna in saida.columns:
        if coluna in pct:
            saida[coluna] = (saida[coluna] * 100).round(1)
        elif pd.api.types.is_float_dtype(saida[coluna]):
            saida[coluna] = saida[coluna].round(2)
    return saida.rename(columns=presentes)


def botoes_exportar(df: pd.DataFrame, nome: str) -> None:
    c1, c2 = st.columns(2)
    c1.download_button("📄 Baixar CSV", df.to_csv(index=False).encode("utf-8"), f"{nome}.csv", "text/csv", key=f"csv_{nome}")
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name=nome[:30])
    c2.download_button("📈 Baixar Excel", buffer.getvalue(), f"{nome}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f"xlsx_{nome}")


COLUNAS_BASE = {
    "ticker": "Papel", "nome": "Empresa", "pais": "País", "setor": "Setor", "preco": "Preço",
    "pl": "P/L", "pvp": "P/VP", "dy": "DY %", "ev_ebit": "EV/EBIT", "roic": "ROIC %", "roe": "ROE %",
    "margem_liquida": "Marg. Líq. %", "divida_patrimonio": "Dív/PL", "liquidez_corrente": "Liq. Corr.",
    "cresc_receita_5a": "Cresc. Rec. %", "earnings_yield": "Earnings Yield %", "bate_inflacao": "Bate inflação?",
}


# ---------------------------------------------------------------------------
# Barra lateral
# ---------------------------------------------------------------------------
fundamentos = carregar_fundamentos()
macro = carregar_macro()
status = carregar_status()

with st.sidebar:
    st.title("📈 Análise de Ações")
    pagina = st.radio("Página", ["Visão geral", "Fórmula Mágica", "Graham", "Dividendos", "Buffett", "Consenso", "Carteira e diversificação", "Histórico"])
    st.markdown("---")
    st.caption(f"Última atualização: {status.get('atualizado_em', 'nunca')}")
    if st.button("🔄 Atualizar dados agora", help="Baixa fundamentos, macro e cotações (pode levar alguns minutos)."):
        with st.spinner("Atualizando..."):
            proc = subprocess.run([sys.executable, "-m", "investimentos.atualizar"], cwd=RAIZ, capture_output=True, text=True)
        if proc.returncode == 0:
            st.success("Dados atualizados.")
        else:
            st.error("Falha na atualização. Veja o log abaixo.")
            st.code(proc.stderr[-3000:])
        st.cache_data.clear()
        st.rerun()
    st.markdown("---")
    st.subheader("Filtros")
    paises = st.multiselect("Mercado", ["BR", "US"], default=["BR", "US"])
    liquidez_br = st.number_input("Volume médio diário mínimo B3 (R$)", min_value=0.0, value=float(config.LIQUIDEZ_MINIMA_BR), step=500_000.0, format="%.0f")
    volume_us = st.number_input("Volume mínimo EUA (US$/dia)", min_value=0.0, value=float(config.VOLUME_MINIMO_US), step=500_000.0, format="%.0f")
    st.markdown("---")
    st.subheader("Parâmetros das estratégias")
    with st.expander("Fórmula Mágica"):
        magica_top = st.slider("Quantidade de ações na lista", 10, 60, config.MAGICA_TOP_N)
    with st.expander("Graham"):
        g_pl = st.slider("P/L máximo", 5.0, 30.0, config.GRAHAM_PL_MAXIMO, 0.5)
        g_pvp = st.slider("P/VP máximo", 0.5, 3.0, config.GRAHAM_PVP_MAXIMO, 0.1)
        g_ms = st.slider("Margem de segurança mínima %", 0, 60, int(config.GRAHAM_MARGEM_SEGURANCA_MINIMA * 100)) / 100
    with st.expander("Dividendos"):
        d_dy = st.slider("DY mínimo % (Bazin usa 6%)", 3.0, 12.0, config.BAZIN_DY_MINIMO * 100, 0.5) / 100
        d_div = st.slider("Dívida/PL máxima", 0.0, 3.0, config.BAZIN_DIVIDA_PATRIMONIO_MAXIMA, 0.1)
    with st.expander("Buffett"):
        b_roe = st.slider("ROE mínimo %", 5, 40, int(config.BUFFETT_ROE_MINIMO * 100)) / 100
        b_mg = st.slider("Margem líquida mínima %", 0, 40, int(config.BUFFETT_MARGEM_LIQUIDA_MINIMA * 100)) / 100
        b_pl = st.slider("P/L máximo (Buffett)", 5.0, 40.0, config.BUFFETT_PL_MAXIMO, 0.5)

if fundamentos.empty:
    st.warning("Ainda não há dados. Clique em **Atualizar dados agora** na barra lateral ou rode `python -m investimentos.atualizar` no terminal.")
    st.stop()

ipca = float(macro.get("ipca_12m") or math.nan)
selic = float(macro.get("selic_meta") or math.nan)
cdi = float(macro.get("cdi_12m") or math.nan)
dolar = float(macro.get("dolar") or math.nan)
taxa_minima = estrategias.taxa_minima_atratividade(ipca, selic=selic)

parametros = {
    "magica": {"top_n": magica_top},
    "graham": {"pl_maximo": g_pl, "pvp_maximo": g_pvp, "margem_seguranca_minima": g_ms},
    "dividendos": {"dy_minimo": d_dy, "divida_patrimonio_maxima": d_div},
    "buffett": {"roe_minimo": b_roe, "margem_liquida_minima": b_mg, "pl_maximo": b_pl},
}
base = fundamentos[fundamentos["pais"].isin(paises)]
base = estrategias.filtrar_liquidez(base, liquidez_minima_br=liquidez_br, volume_minimo_us=volume_us)
ranking = estrategias.consolidar(base, taxa_minima=taxa_minima, parametros=parametros)


def cabecalho_macro() -> None:
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("IPCA 12 meses", _pct(ipca), help=f"Último mês: {macro.get('ipca_mes_referencia') or '—'}")
    c2.metric("Selic (meta)", _pct(selic))
    c3.metric("CDI 12 meses", _pct(cdi))
    c4.metric("Dólar", _moeda(dolar), help=str(macro.get("fonte_dolar") or ""))
    c5.metric("Taxa mínima de atratividade", _pct(taxa_minima), help="Maior entre IPCA + prêmio de risco e a Selic. Earnings yield (1/P/L) abaixo disso não compensa o risco.")


def mostrar_lista(df: pd.DataFrame, colunas_extra: dict[str, str], nome: str, destaque: str) -> None:
    colunas = {**{k: v for k, v in COLUNAS_BASE.items() if k in ("ticker", "nome", "pais", "setor", "preco")}, **colunas_extra,
               **{k: v for k, v in COLUNAS_BASE.items() if k not in ("ticker", "nome", "pais", "setor", "preco") and k not in colunas_extra}}
    st.dataframe(tabela_formatada(df, colunas), use_container_width=True, hide_index=True, height=min(800, 60 + 35 * len(df)))
    botoes_exportar(tabela_formatada(df, colunas), nome)
    if destaque in df.columns and df[destaque].notna().any():
        top = df.head(20)
        fig = px.bar(top, x="ticker", y=destaque, color="pais", title=f"Top 20 por {colunas.get(destaque, destaque)}")
        st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Páginas
# ---------------------------------------------------------------------------
if pagina == "Visão geral":
    st.title("Visão geral do dia")
    cabecalho_macro()
    etapas = status.get("etapas", {})
    falhas = [k for k, v in etapas.items() if not v.get("ok")]
    if falhas:
        st.warning("Fontes com falha na última atualização: " + ", ".join(falhas) + ". Os dados dessas fontes são da execução anterior.")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Papéis analisados", len(ranking))
    c2.metric("Aprovados na Fórmula Mágica", int(ranking["aprovado_magica"].sum()))
    c3.metric("Aprovados em Graham", int(ranking["aprovado_graham"].sum()))
    c4.metric("Aprovados em Dividendos", int(ranking["aprovado_dividendos"].sum()))

    st.subheader("Consenso: aprovadas em 2 ou mais estratégias")
    consenso = ranking[ranking["qtd_estrategias_aprovado"] >= 2]
    if consenso.empty:
        st.info("Nenhum papel aprovado em duas estratégias ao mesmo tempo com os parâmetros atuais. Veja a página Consenso para a pontuação geral.")
    else:
        st.dataframe(tabela_formatada(consenso, {"ticker": "Papel", "nome": "Empresa", "pais": "País", "preco": "Preço", "estrategias_aprovado": "Aprovado em", "pontuacao_geral": "Pontuação", "pl": "P/L", "pvp": "P/VP", "dy": "DY %", "roe": "ROE %", "earnings_yield": "Earnings Yield %"}), use_container_width=True, hide_index=True)

    st.subheader("Top 10 de cada estratégia")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Fórmula Mágica**")
        st.dataframe(tabela_formatada(ranking[ranking["posicao_magica"].notna()].sort_values("posicao_magica").head(10), {"posicao_magica": "#", "ticker": "Papel", "pais": "País", "ev_ebit": "EV/EBIT", "roic": "ROIC %"}), hide_index=True, use_container_width=True)
        st.markdown("**Dividendos (Bazin / Barsi)**")
        st.dataframe(tabela_formatada(ranking.sort_values(["pontos_dividendos", "dy"], ascending=False).head(10), {"ticker": "Papel", "pais": "País", "dy": "DY %", "preco": "Preço", "preco_teto_bazin": "Preço teto", "desconto_preco_teto": "Desconto %"}), hide_index=True, use_container_width=True)
    with c2:
        st.markdown("**Graham**")
        st.dataframe(tabela_formatada(ranking.sort_values(["pontos_graham", "margem_seguranca_graham"], ascending=False).head(10), {"ticker": "Papel", "pais": "País", "preco": "Preço", "preco_justo_graham": "Preço justo", "margem_seguranca_graham": "Margem seg. %"}), hide_index=True, use_container_width=True)
        st.markdown("**Buffett**")
        st.dataframe(tabela_formatada(ranking.sort_values(["pontos_buffett", "rank_qualidade"], ascending=[False, True]).head(10), {"ticker": "Papel", "pais": "País", "roe": "ROE %", "margem_liquida": "Marg. Líq. %", "pl": "P/L", "divida_patrimonio": "Dív/PL"}), hide_index=True, use_container_width=True)

elif pagina == "Fórmula Mágica":
    st.title("Fórmula Mágica (Joel Greenblatt)")
    st.markdown("Ranking combinado de **EV/EBIT** (quanto menor, mais barata a empresa) e **ROIC** (quanto maior, melhor o negócio). "
                "Greenblatt sugere comprar as 20 a 30 primeiras, manter por um ano e repetir. Empresas com EV/EBIT ou ROIC negativos são excluídas.")
    lista = ranking[ranking["posicao_magica"].notna()].sort_values("posicao_magica")
    so_aprovados = st.checkbox("Mostrar só a lista final", value=True)
    if so_aprovados:
        lista = lista[lista["aprovado_magica"]]
    mostrar_lista(lista, {"posicao_magica": "#", "ev_ebit": "EV/EBIT", "roic": "ROIC %", "rank_ev_ebit": "Rank EV/EBIT", "rank_roic": "Rank ROIC", "pontos_magica": "Soma ranks"}, "formula_magica", "roic")

elif pagina == "Graham":
    st.title("Valor (Benjamin Graham)")
    st.markdown("Critérios do *Investidor Inteligente*: P/L ≤ 15, P/VP ≤ 1,5, P/L × P/VP ≤ 22,5, liquidez corrente ≥ 1,5, dívida ≤ patrimônio e "
                "**margem de segurança** sobre o preço justo = √(22,5 × LPA × VPA). Cada critério atendido vale 1 ponto.")
    lista = ranking.sort_values(["pontos_graham", "margem_seguranca_graham"], ascending=False)
    minimo = st.slider("Pontos mínimos (7 = todos os critérios)", 0, 7, 7)
    lista = lista[lista["pontos_graham"] >= minimo]
    mostrar_lista(lista, {"pontos_graham": "Pontos", "preco_justo_graham": "Preço justo", "margem_seguranca_graham": "Margem seg. %", "pl_x_pvp": "P/L × P/VP", "lpa": "LPA", "vpa": "VPA"}, "graham", "margem_seguranca_graham")

elif pagina == "Dividendos":
    st.title("Dividendos (Décio Bazin e Luiz Barsi)")
    st.markdown("Bazin: só compra quem paga **DY ≥ 6%**, e o **preço teto** é dividendo por ação ÷ 6%. Barsi acrescenta dívida controlada e preferência por setores perenes "
                "(bancos, energia, saneamento, seguros e telecom), que ganham meio ponto extra. Lembre que DY passado não garante DY futuro: confira se o lucro sustenta o pagamento.")
    lista = ranking.sort_values(["pontos_dividendos", "dy"], ascending=False)
    so_aprovados = st.checkbox("Mostrar só aprovadas (todos os critérios)", value=True)
    if so_aprovados:
        lista = lista[lista["aprovado_dividendos"]]
    mostrar_lista(lista, {"dy": "DY %", "dpa": "Div./ação", "preco_teto_bazin": "Preço teto", "desconto_preco_teto": "Desconto s/ teto %", "setor_barsi": "Setor perene", "pontos_dividendos": "Pontos"}, "dividendos", "dy")

elif pagina == "Buffett":
    st.title("Qualidade (Warren Buffett)")
    st.markdown("Empresas boas a preço razoável: **ROE ≥ 15%**, margem líquida ≥ 10%, dívida ≤ 50% do patrimônio, receita crescendo, P/L ≤ 20 e P/VP ≤ 3. "
                "Os números não capturam vantagem competitiva e gestão, que você avalia lendo sobre a empresa.")
    lista = ranking.sort_values(["pontos_buffett", "rank_qualidade"], ascending=[False, True])
    minimo = st.slider("Pontos mínimos (6 = todos os critérios)", 0, 6, 6)
    lista = lista[lista["pontos_buffett"] >= minimo]
    mostrar_lista(lista, {"pontos_buffett": "Pontos", "roe": "ROE %", "margem_liquida": "Marg. Líq. %", "divida_patrimonio": "Dív/PL", "cresc_receita_5a": "Cresc. Rec. %"}, "buffett", "roe")

elif pagina == "Consenso":
    st.title("Consenso entre estratégias")
    st.markdown("Pontuação geral = 10 pontos por estratégia aprovada + pontos parciais de Graham, Dividendos e Buffett + bônus pela posição na Fórmula Mágica. "
                "Quanto mais métodos diferentes concordam, menor a chance de o preço baixo ser uma armadilha.")
    minimo = st.slider("Mínimo de estratégias aprovadas", 0, 4, 1)
    so_inflacao = st.checkbox("Só quem bate a taxa mínima de atratividade (earnings yield)", value=False)
    lista = ranking[ranking["qtd_estrategias_aprovado"] >= minimo]
    if so_inflacao:
        lista = lista[lista["bate_inflacao"] == True]  # noqa: E712
    mostrar_lista(lista, {"pontuacao_geral": "Pontuação", "qtd_estrategias_aprovado": "Nº estratégias", "estrategias_aprovado": "Aprovado em", "posicao_magica": "# Mágica", "margem_seguranca_graham": "Margem Graham %", "desconto_preco_teto": "Desconto Bazin %", "pontos_buffett": "Pts Buffett"}, "consenso", "pontuacao_geral")
    st.subheader("Mapa: preço x qualidade")
    disp = ranking[(ranking["pl"] > 0) & (ranking["pl"] < 60) & ranking["roe"].notna()]
    if not disp.empty:
        fig = px.scatter(disp, x="pl", y="roe", color="pais", hover_name="ticker", size="qtd_estrategias_aprovado", size_max=18,
                         labels={"pl": "P/L", "roe": "ROE"}, title="Canto superior esquerdo = barata e rentável")
        fig.update_yaxes(tickformat=".0%")
        st.plotly_chart(fig, use_container_width=True)

elif pagina == "Carteira e diversificação":
    st.title("Carteira e diversificação")
    arquivo = config.ARQUIVO_CARTEIRA if config.ARQUIVO_CARTEIRA.exists() else config.ARQUIVO_CARTEIRA_EXEMPLO
    if arquivo == config.ARQUIVO_CARTEIRA_EXEMPLO:
        st.info("Mostrando a carteira de exemplo. Copie `investimentos/carteira_exemplo.csv` para `investimentos/carteira.csv` e preencha com as suas posições.")
    try:
        cart = mod_carteira.carregar_carteira(arquivo)
    except ValueError as erro:
        st.error(str(erro))
        st.stop()
    cotacoes = carregar_cotacoes()
    precos = dict(zip(fundamentos["ticker"], fundamentos["preco"]))
    precos.update(dict(zip(cotacoes["ticker"].astype(str), cotacoes["preco"])))
    avaliada = mod_carteira.avaliar_carteira(cart, precos, dolar)
    res = mod_carteira.resumo(avaliada)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Patrimônio (R$)", _moeda(res["valor_brl"]))
    c2.metric("Custo (R$)", _moeda(res["custo_brl"]))
    c3.metric("Resultado", _moeda(res["resultado_brl"]), _pct(res["resultado_pct"]))
    c4.metric("Retorno real necessário", _pct(ipca), help="Inflação dos últimos 12 meses: abaixo disso a carteira perdeu poder de compra.")
    if res["sem_cotacao"]:
        st.warning(f"{res['sem_cotacao']} posição(ões) sem cotação: foi usado o preço médio. Rode a atualização ou preencha `valor_atual`.")

    st.subheader("Posições")
    st.dataframe(tabela_formatada(avaliada, {"ticker": "Ativo", "descricao": "Descrição", "tipo": "Tipo", "moeda": "Moeda", "quantidade": "Qtd", "preco_medio": "Preço médio", "preco_atual": "Preço atual", "valor": "Valor (moeda)", "valor_brl": "Valor (R$)", "resultado_pct": "Resultado %"}), use_container_width=True, hide_index=True)

    c1, c2 = st.columns(2)
    por_tipo = mod_carteira.alocacao(avaliada, "tipo", config.ALOCACAO_ALVO_TIPO)
    por_moeda = mod_carteira.alocacao(avaliada, "moeda", config.ALOCACAO_ALVO_MOEDA)
    with c1:
        st.subheader("Por tipo de ativo")
        fig = px.pie(avaliada, values="valor_brl", names="tipo", hole=0.4)
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(tabela_formatada(por_tipo, {"tipo": "Tipo", "valor_brl": "Valor (R$)", "pct_atual": "Atual %", "pct_alvo": "Alvo %", "diferenca_pp": "Diferença p.p.", "valor_para_alvo": "Falta p/ alvo (R$)"}), hide_index=True, use_container_width=True)
    with c2:
        st.subheader("Por moeda")
        fig = px.pie(avaliada, values="valor_brl", names="moeda", hole=0.4)
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(tabela_formatada(por_moeda, {"moeda": "Moeda", "valor_brl": "Valor (R$)", "pct_atual": "Atual %", "pct_alvo": "Alvo %", "diferenca_pp": "Diferença p.p.", "valor_para_alvo": "Falta p/ alvo (R$)"}), hide_index=True, use_container_width=True)
    st.caption("Alvos definidos em `investimentos/config.py` (ALOCACAO_ALVO_TIPO e ALOCACAO_ALVO_MOEDA).")

    st.subheader("Onde colocar o próximo aporte")
    aporte = st.number_input("Valor do aporte (R$)", min_value=0.0, value=1000.0, step=100.0)
    if aporte > 0:
        sugestao = mod_carteira.sugerir_aporte(avaliada, aporte, config.ALOCACAO_ALVO_TIPO, "tipo")
        st.dataframe(tabela_formatada(sugestao, {"tipo": "Tipo", "aporte_sugerido": "Aporte sugerido (R$)"}), hide_index=True, use_container_width=True)
        tipos_acao = sugestao[sugestao["tipo"].isin(["Ação BR", "Ação US"])]["tipo"].tolist()
        if tipos_acao:
            st.markdown("**Candidatas (consenso) para esses tipos:**")
            for tipo in tipos_acao:
                pais = "BR" if tipo == "Ação BR" else "US"
                cand = ranking[(ranking["pais"] == pais) & (ranking["qtd_estrategias_aprovado"] >= 1)].head(8)
                st.markdown(f"*{tipo}*")
                st.dataframe(tabela_formatada(cand, {"ticker": "Papel", "preco": "Preço", "estrategias_aprovado": "Aprovado em", "pontuacao_geral": "Pontuação", "dy": "DY %", "pl": "P/L"}), hide_index=True, use_container_width=True)
    if not cotacoes.empty:
        st.subheader("Referências de ETFs")
        st.dataframe(cotacoes[["ticker", "descricao", "preco", "data"]].rename(columns={"ticker": "ETF", "descricao": "Descrição", "preco": "Preço", "data": "Data"}), hide_index=True, use_container_width=True)

elif pagina == "Histórico":
    st.title("Histórico das análises")
    hist = carregar_historico()
    if hist.empty:
        st.info("O histórico é gravado a cada atualização em `investimentos/data/historico/`. Rode a atualização por alguns dias para ver a evolução.")
    else:
        datas = sorted(hist["data"].unique())
        st.caption(f"{len(datas)} dia(s) de histórico, de {datas[0]} a {datas[-1]}.")
        if len(datas) >= 2:
            ultimo, anterior = datas[-1], datas[-2]
            cons_hoje = set(hist[(hist["data"] == ultimo) & (hist["qtd_estrategias_aprovado"] >= 1)]["ticker"])
            cons_ontem = set(hist[(hist["data"] == anterior) & (hist["qtd_estrategias_aprovado"] >= 1)]["ticker"])
            c1, c2 = st.columns(2)
            c1.success("Entraram nas listas: " + (", ".join(sorted(cons_hoje - cons_ontem)) or "nenhum"))
            c2.error("Saíram das listas: " + (", ".join(sorted(cons_ontem - cons_hoje)) or "nenhum"))
        ticker = st.selectbox("Papel", sorted(hist["ticker"].unique()))
        serie = hist[hist["ticker"] == ticker].sort_values("data")
        c1, c2 = st.columns(2)
        c1.plotly_chart(px.line(serie, x="data", y="preco", markers=True, title=f"{ticker}: preço"), use_container_width=True)
        c2.plotly_chart(px.line(serie, x="data", y="pontuacao_geral", markers=True, title=f"{ticker}: pontuação geral"), use_container_width=True)
        st.dataframe(serie, hide_index=True, use_container_width=True)

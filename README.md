# Ferramenta de análise diária de ações

Ferramenta que baixa, todo dia, os
fundamentos das ações da B3 e de uma lista de ações americanas, aplica os
métodos clássicos de seleção e mostra tudo num painel Streamlit, junto com
inflação, Selic, CDI, dólar e a sua carteira.

## O que ela faz

| Página | Conteúdo |
|---|---|
| Visão geral | IPCA (12m, no ano, esperado pelo Focus), IGP-M, Selic, CDI, juro real, dólar, taxa mínima de atratividade e o top 10 de cada método |
| Fórmula Mágica | Ranking de Greenblatt (EV/EBIT baixo + ROIC alto) |
| Graham | P/L, P/VP, P/L x P/VP, liquidez corrente, dívida e margem de segurança sobre o preço justo √(22,5 x LPA x VPA) |
| Dividendos | Método Bazin (DY ≥ 6%, preço teto = DPA / 6%) com os setores perenes de Barsi |
| Buffett | ROE, margem líquida, dívida, crescimento de receita e preço razoável |
| Consenso | Papéis aprovados em mais de um método, pontuação geral e mapa P/L x ROE |
| Carteira e diversificação | Valor da carteira, alocação por tipo e por moeda versus alvo, e sugestão de onde direcionar o próximo aporte |
| Histórico | Quem entrou e saiu das listas desde a última atualização e a evolução de cada papel |

Todos os limites (DY mínimo, P/L máximo, ROE mínimo etc.) ficam em
`investimentos/config.py` e também podem ser ajustados ao vivo na barra lateral do painel.

## Fontes de dados (todas gratuitas, sem chave)

- **Fundamentus** (`fundamentus.com.br/resultado.php`): todos os papéis da B3 com
  P/L, P/VP, DY, EV/EBIT, ROIC, ROE, margens, volume médio diário ("Liq.2meses") e dívida. O setor de cada
  papel vem da página de detalhes e fica em cache em `investimentos/data/setores_br.csv`.
- **Yahoo Finance** (biblioteca `yfinance`): fundamentos das ações americanas da
  lista `TICKERS_US`, cotações dos ETFs e dos ativos da carteira, dólar reserva.
- **Banco Central (API SGS)**: IPCA mensal (433), IGP-M mensal (189), meta Selic (432),
  CDI diário (12, com reserva no CDI anualizado 4389) e dólar PTAX (1). Expectativa de IPCA
  12 meses do boletim Focus (API Olinda).

Se uma fonte falhar, a ferramenta mantém os dados da execução anterior e
registra a falha e os avisos da execução em `investimentos/data/ultima_atualizacao.json`
(o painel avisa).

## Como usar

```bash
pip install -r requirements.txt           # na raiz do repositório
python -m investimentos.atualizar         # baixa tudo e gera investimentos/data/
streamlit run investimentos/app_investimentos.py
```

No Windows basta dar dois cliques em `rodar_investimentos.bat` (atualiza e
abre o painel). Opções úteis:

```bash
python -m investimentos.atualizar --sem-us        # só Brasil, bem mais rápido
python -m investimentos.atualizar --sem-setores   # não consulta setor por papel
```

### Sua carteira

Copie `investimentos/carteira_exemplo.csv` para `investimentos/carteira.csv` (este arquivo está no
`.gitignore`, não vai para o GitHub) e preencha:

| coluna | significado |
|---|---|
| ticker | PETR4, MXRF11, AAPL, VOO... Vazio para renda fixa e caixa |
| tipo | Ação BR, FII, Ação US, ETF US, Renda Fixa BR, Renda Fixa US, Cripto ou Caixa |
| moeda | BRL ou USD |
| quantidade, preco_medio | na moeda do ativo |
| valor_atual | opcional: valor de mercado informado por você (renda fixa, caixa, cripto) |
| descricao | texto livre |

As metas de alocação por tipo e por moeda ficam em `config.py`
(`ALOCACAO_ALVO_TIPO`, `ALOCACAO_ALVO_MOEDA`).

## Atualização automática todo dia

### Opção 1: GitHub Actions (recomendada, não depende do seu PC ligado)

O workflow `.github/workflows/atualizar_investimentos.yml` roda de segunda a
sexta às 20h30 (horário de Brasília), depois do fechamento dos mercados, e
faz commit dos arquivos de `investimentos/data/`. Para ativar:

1. O agendamento só roda no branch padrão (`main`).
2. Em *Settings > Actions > General > Workflow permissions*, marque
   **Read and write permissions**.
3. Para testar na hora: aba *Actions > Atualizar dados de investimentos > Run workflow*.

Se você publicar o painel no Streamlit Cloud (gratuito),
aponte-o para `investimentos/app_investimentos.py`: ele lê os CSVs do
repositório, então cada commit do workflow atualiza o painel sozinho.

### Opção 2: Agendador de Tarefas do Windows

Crie uma tarefa diária que execute `atualizar_investimentos.bat` (ele grava o
log em `investimentos/data/atualizacao.log`).

## Estrutura

```
investimentos/
├── app_investimentos.py   painel Streamlit
├── atualizar.py           pipeline diário (python -m investimentos.atualizar)
├── config.py              parâmetros das estratégias, listas de tickers, alocação alvo
├── estrategias.py         Fórmula Mágica, Graham, Bazin/Barsi, Buffett e consolidação
├── carteira.py            valorização, diversificação e sugestão de aporte
├── fontes/
│   ├── comum.py           esquema comum + conversão de números no formato brasileiro
│   ├── fundamentus.py     ações da B3
│   ├── yahoo.py           ações americanas, ETFs, cotações, dólar
│   └── bcb.py             IPCA, Selic, CDI, PTAX
├── data/                  gerado pela atualização (fundamentos.csv, ranking.csv, macro.json, cotacoes.csv)
│   └── historico/         um ranking compacto por dia
├── tests/                 pytest, sem acesso à internet
└── carteira_exemplo.csv
```

Rodar os testes: `python -m pytest`.

Se a atualização falhar no seu computador, rode `python -m investimentos.diagnostico`:
ele testa cada biblioteca e cada site e imprime um relatório para identificar a causa.

## Avisos

- Os indicadores são "trailing" (últimos 12 meses). Um DY alto pode ser um
  dividendo extraordinário que não se repete; um P/L baixo pode ser lucro
  não recorrente. Use as listas como ponto de partida para estudar a empresa,
  não como ordem de compra.
- Fundamentus e Yahoo são sites de terceiros sem garantia de disponibilidade
  ou de formato. Se o layout mudar, o parser em `fontes/fundamentus.py` precisa
  ser ajustado (os testes em `tests/` mostram o formato esperado).
- Nada aqui é recomendação de investimento.

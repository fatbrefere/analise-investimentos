"""HTML sintético com a mesma estrutura da página resultado.php do Fundamentus."""

CABECALHO = [
    "Papel", "Cotação", "P/L", "P/VP", "PSR", "Div.Yield", "P/Ativo", "P/Cap.Giro", "P/EBIT",
    "P/Ativ Circ.Liq", "EV/EBIT", "EV/EBITDA", "Mrg Ebit", "Mrg. Líq.", "Liq. Corr.", "ROIC", "ROE",
    "Liq.2meses", "Patrim. Líq", "Dív.Brut/ Patrim.", "Cresc. Rec.5a",
]

LINHAS = [
    # Papel, Cotação, P/L, P/VP, PSR, DY, P/Ativo, P/CapGiro, P/EBIT, P/ACL, EV/EBIT, EV/EBITDA, MrgEbit, MrgLiq, LiqCorr, ROIC, ROE, Liq2m, PL, Div/PL, Cresc
    ["PETR4", "32,50", "4,10", "1,05", "0,80", "15,20%", "0,45", "-3,10", "3,00", "-1,20", "3,50", "2,80", "35,00%", "20,10%", "0,95", "25,30%", "26,00%", "1.500.000.000,00", "380.000.000.000", "0,70", "8,50%"],
    ["ITSA4", "9,80", "6,20", "1,10", "2,50", "8,10%", "0,70", "5,00", "5,80", "-2,00", "5,50", "5,20", "40,00%", "38,00%", "2,10", "14,00%", "18,00%", "250.000.000,00", "80.000.000.000", "0,10", "6,00%"],
    ["TAEE11", "34,00", "7,50", "1,60", "4,00", "9,50%", "0,55", "6,00", "6,50", "-1,50", "8,00", "7,00", "60,00%", "50,00%", "1,80", "12,00%", "21,00%", "90.000.000,00", "7.500.000.000", "0,90", "9,00%"],
    ["WEGE3", "40,00", "30,00", "8,00", "5,00", "1,20%", "3,50", "9,00", "25,00", "20,00", "24,00", "21,00", "18,00%", "16,00%", "2,20", "28,00%", "30,00%", "300.000.000,00", "16.000.000.000", "0,20", "20,00%"],
    ["MGLU3", "2,00", "-15,00", "1,30", "0,30", "0,00%", "0,25", "-2,00", "-30,00", "-1,00", "-20,00", "15,00", "-2,00%", "-3,00%", "1,10", "-1,50%", "-8,00%", "120.000.000,00", "11.000.000.000", "1,20", "5,00%"],
    ["ILIQ3", "5,00", "3,00", "0,40", "0,20", "12,00%", "0,20", "1,00", "2,50", "0,50", "2,00", "1,80", "15,00%", "10,00%", "2,50", "20,00%", "15,00%", "50.000,00", "900.000.000", "0,30", "2,00%"],
    ["BBAS3", "28,00", "4,50", "0,85", "1,10", "9,00%", "0,05", "0,00", "0,00", "0,00", "0,00", "0,00", "0,00%", "25,00%", "0,00", "0,00%", "20,00%", "800.000.000,00", "170.000.000.000", "0,00", "12,00%"],
    ["SANB11", "-", "-", "-", "-", "-", "-", "-", "-", "-", "-", "-", "-", "-", "-", "-", "-", "-", "-", "-", "-"],
]


def html_resultado() -> str:
    cabecalho = "".join(f"<th><a href='#'>{c}</a></th>" for c in CABECALHO)
    corpo = "".join("<tr>" + "".join(f"<td>{celula}</td>" for celula in linha) + "</tr>" for linha in LINHAS)
    return f"""<html><head><meta charset="utf-8"></head><body>
    <table id="outra"><tr><th>Nada</th></tr><tr><td>1</td></tr></table>
    <table id="resultado"><thead><tr>{cabecalho}</tr></thead><tbody>{corpo}</tbody></table>
    </body></html>"""


def html_detalhes() -> str:
    return """<html><body><table>
    <tr><td class="label"><span class="help">?</span>Papel</td><td class="data"><span>PETR4</span></td>
        <td class="label">Cotação</td><td class="data">32,50</td></tr>
    <tr><td class="label">Empresa</td><td class="data">PETROBRAS PN</td><td class="label">Data últ cot</td><td class="data">26/10/2026</td></tr>
    <tr><td class="label"><span class="help">?</span>Setor</td><td class="data">Petróleo, Gás e Biocombustíveis</td><td class="label">Min 52 sem</td><td class="data">28,00</td></tr>
    <tr><td class="label">Subsetor</td><td class="data">Exploração, Refino e Distribuição</td><td class="label">Max 52 sem</td><td class="data">42,00</td></tr>
    </table></body></html>"""

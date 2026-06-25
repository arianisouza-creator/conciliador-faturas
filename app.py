import io
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional

import pandas as pd
import pypdf
try:
    from fpdf import FPDF
except ImportError:  # pragma: no cover - fallback for local parsing/tests
    FPDF = None

try:
    import streamlit as st
except ImportError:  # pragma: no cover - fallback for local parsing/tests
    class _StreamlitFallback:
        def set_page_config(self, *args, **kwargs):
            return None

        def title(self, *args, **kwargs):
            return None

        def write(self, *args, **kwargs):
            return None

        def file_uploader(self, *args, **kwargs):
            return None

        def selectbox(self, *args, **kwargs):
            return None

        def text_input(self, *args, **kwargs):
            return ""

        def button(self, *args, **kwargs):
            return False

        def subheader(self, *args, **kwargs):
            return None

        def dataframe(self, *args, **kwargs):
            return None

        def info(self, *args, **kwargs):
            return None

        def warning(self, *args, **kwargs):
            return None

        def error(self, *args, **kwargs):
            return None

        def download_button(self, *args, **kwargs):
            return None

        def markdown(self, *args, **kwargs):
            return None

        def stop(self):
            raise SystemExit

    st = _StreamlitFallback()


st.set_page_config(page_title="Conciliador de Cartao", layout="wide")


TOLERANCIA_VALOR = Decimal("0.20")

CSS_APP = """
<style>
:root {
    --mse: #e91e4f;
    --dark: #1e293b;
    --bg: #f5f7fb;
    --pendente: #facc15;
    --estorno: #ef4444;
    --duplicado: #3b82f6;
}

html, body, [class*="css"] {
    font-family: Arial, Helvetica, sans-serif;
}

body {
    background: var(--bg);
}

div.block-container {
    padding-top: 1rem;
    padding-bottom: 1.25rem;
    max-width: 1600px;
}

.stApp {
    background: var(--bg);
}

.mse-topbar {
    background: var(--dark);
    color: white;
    border-radius: 0 0 10px 10px;
    padding: 10px 16px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin: 0 0 18px 0;
    position: sticky;
    top: 0;
    z-index: 20;
    box-shadow: 0 8px 22px rgba(15, 23, 42, 0.18);
}

.mse-brand {
    display: flex;
    align-items: center;
    gap: 10px;
    font-weight: 700;
}

.small-muted {
    color: #94a3b8;
    font-size: 12px;
}

.app-title {
    color: #0f172a;
    font-size: 36px;
    line-height: 1.1;
    font-weight: 800;
    margin: 14px 0 10px 0;
}

.app-subtitle {
    color: #475569;
    font-size: 15px;
    margin-bottom: 22px;
}

.panel {
    background: #ffffff;
    border: 1px solid #d7deea;
    border-radius: 10px;
    padding: 14px;
    margin-bottom: 16px;
    box-shadow: 0 2px 6px rgba(15, 23, 42, 0.05);
}

.panel-title {
    font-weight: 800;
    color: #0f172a;
    font-size: 16px;
    margin: 0 0 10px 0;
}

.summary-row {
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    margin: 8px 0 10px 0;
}

.summary-card {
    background: #fff;
    border: 1px solid #dbe2ee;
    border-radius: 10px;
    padding: 10px 14px;
    min-width: 140px;
}

.summary-label {
    font-size: 12px;
    color: #64748b;
    margin-bottom: 2px;
}

.summary-value {
    font-size: 18px;
    font-weight: 800;
    color: #0f172a;
}

.chip {
    display: inline-block;
    border-radius: 999px;
    padding: 3px 10px;
    font-size: 12px;
    font-weight: 700;
}

.chip-ok { background: #dcfce7; color: #166534; }
.chip-pendente { background: #fef3c7; color: #92400e; }
.chip-estorno { background: #fee2e2; color: #991b1b; }
.chip-duplicado { background: #dbeafe; color: #1d4ed8; }

.table-wrap {
    overflow-x: auto;
    border: 1px solid #111827;
    border-radius: 8px;
    background: white;
}

.mse-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}

.row-estorno td { background: #fee2e2 !important; color: #b91c1c !important; }
.row-pendente td { background: #fef3c7 !important; color: #92400e !important; }
.row-duplicado td { background: #dbeafe !important; color: #1d4ed8 !important; }
.row-ok td { background: #ffffff !important; color: #111827 !important; }

thead th {
    background: #e5e7eb;
    color: #0f172a;
    border: 1px solid #111827;
    padding: 8px;
    text-align: left;
    font-weight: 700;
}

tbody td {
    border: 1px solid #111827;
    padding: 7px 8px;
    vertical-align: top;
}

.controls-row {
    display: grid;
    grid-template-columns: 1.6fr 1.6fr 1fr auto;
    gap: 14px;
    align-items: end;
}

@media (max-width: 1200px) {
    .controls-row {
        grid-template-columns: 1fr;
    }
}
</style>
"""


@dataclass
class LancamentoFatura:
    data: str
    descricao: str
    valor_texto: str
    valor: Decimal
    localizador: Optional[str] = None
    bruto_texto: str = ""


@dataclass
class ReferenciaPedido:
    origem_arquivo: str
    origem_tipo: str
    pedido: str
    valor_texto: str
    valor: Decimal
    descricao: str
    datas: List[str] = field(default_factory=list)
    localizador: Optional[str] = None
    intine: Optional[str] = None


def ascii_fold(texto: str) -> str:
    if not texto:
        return ""
    texto = unicodedata.normalize("NFKD", texto)
    texto = texto.encode("ascii", "ignore").decode("ascii")
    texto = texto.replace("\xa0", " ")
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip().upper()


def moeda_para_decimal(valor: str) -> Optional[Decimal]:
    if not valor:
        return None
    try:
        normalizado = valor.strip().replace(".", "").replace(",", ".")
        return Decimal(normalizado)
    except (InvalidOperation, AttributeError):
        return None


def normalizar_data(data: str) -> str:
    match = re.match(r"(\d{2}/\d{2})", data or "")
    return match.group(1) if match else (data or "").strip()


def ler_pdf_bytes(conteudo_bytes: bytes) -> str:
    texto = []
    reader = pypdf.PdfReader(io.BytesIO(conteudo_bytes))
    for pagina in reader.pages:
        texto.append(pagina.extract_text() or "")
    return "\n".join(texto)


def salvar_nome_titular(cand: str) -> str:
    cand = ascii_fold(cand)
    cand = re.sub(r"^(TOTAL PARA|CARTAO|CARTAO:)\s+", "", cand).strip()
    return cand


def detectar_titulares(texto_fatura: str) -> List[str]:
    candidatos = []
    for linha in texto_fatura.splitlines():
        linha_busca = ascii_fold(linha)
        m1 = re.match(
            r"^([A-Z][A-Z ]{3,80}?)\s+CARTAO\s+\d{4}\s+XXXX\s+XXXX\s+\d{4}\b",
            linha_busca,
        )
        m2 = re.match(
            r"^([A-Z][A-Z ]{3,80}?)\s+\d{4}\s+XXXX\s+XXXX\s+\d{4}\b",
            linha_busca,
        )
        nome = None
        if m1:
            nome = salvar_nome_titular(m1.group(1))
        elif m2 and "TRANSACOES" not in linha_busca:
            nome = salvar_nome_titular(m2.group(1))

        if nome and len(nome.split()) >= 2:
            candidatos.append(nome)

    vistos = []
    for nome in candidatos:
        if nome not in vistos:
            vistos.append(nome)
    return vistos


def localizar_secao_titular(texto_fatura: str, nome_titular: str) -> str:
    linhas = texto_fatura.splitlines()
    nome_busca = ascii_fold(nome_titular)

    cabecalhos = []
    for idx, linha in enumerate(linhas):
        linha_busca = ascii_fold(linha)
        if re.search(
            r"^[A-Z][A-Z ]{3,80}\s+CARTAO\s+\d{4}\s+XXXX\s+XXXX\s+\d{4}\b",
            linha_busca,
        ):
            cabecalhos.append(idx)
        elif re.search(
            r"^[A-Z][A-Z ]{3,80}\s+\d{4}\s+XXXX\s+XXXX\s+\d{4}\b",
            linha_busca,
        ) and "TRANSACOES" not in linha_busca:
            cabecalhos.append(idx)

    inicio = None
    for idx in cabecalhos:
        linha_busca = ascii_fold(linhas[idx])
        if nome_busca in linha_busca:
            inicio = idx
            break

    if inicio is None:
        return ""

    fim = len(linhas)
    for idx in cabecalhos:
        if idx > inicio:
            fim = idx
            break

    secao = linhas[inicio:fim]
    return "\n".join(secao)


def localizar_secao_santander(texto_fatura: str, nome_titular: str) -> str:
    linhas = texto_fatura.splitlines()
    nome_busca = ascii_fold(nome_titular)
    inicio = None
    fim = len(linhas)

    for idx, linha in enumerate(linhas):
        linha_busca = ascii_fold(linha)
        if nome_busca in linha_busca and re.search(r"\d{4}\s+XXXX\s+XXXX\s+\d{4}", linha_busca):
            inicio = idx
            break

    if inicio is None:
        return ""

    for idx in range(inicio + 1, len(linhas)):
        linha_busca = ascii_fold(linhas[idx])
        if re.search(r"^[A-Z][A-Z ]{3,80}\s+\d{4}\s+XXXX\s+XXXX\s+\d{4}\b", linha_busca) and nome_busca not in linha_busca:
            fim = idx
            break
        if linha_busca.startswith("TOTAL EM R$"):
            fim = idx
            break

    return "\n".join(linhas[inicio:fim])


def agrupar_blocos_transacao(linhas: List[str]) -> List[List[str]]:
    blocos = []
    atual = []
    for linha in linhas:
        linha_limpa = linha.strip()
        if not linha_limpa:
            continue

        linha_busca = ascii_fold(linha_limpa)
        if linha_busca.startswith("TOTAL PARA"):
            break

        if re.match(r"^\d{2}/\d{2}\b", linha_busca):
            if atual:
                blocos.append(atual)
            atual = [linha_limpa]
        elif atual:
            atual.append(linha_limpa)

    if atual:
        blocos.append(atual)
    return blocos


def extrair_localizador(texto_busca: str) -> Optional[str]:
    excluidos = {
        "CARTAO",
        "TOTAL",
        "PARA",
        "PAGTO",
        "POR",
        "DEB",
        "EM",
        "CC",
        "CUSTO",
        "TRANS",
        "EXTERIOR",
        "IOF",
    }
    tokens = re.findall(r"\b[A-Z0-9]{6}\b", texto_busca)
    for token in reversed(tokens):
        if token not in excluidos and not token.isdigit():
            return token
    return None


def extrair_lancamento_bloco(bloco: List[str]) -> Optional[LancamentoFatura]:
    texto_original = " ".join(bloco)
    texto_busca = ascii_fold(texto_original)

    data_match = re.search(r"\b(\d{2}/\d{2})\b", texto_busca)
    if not data_match:
        return None

    valores = re.findall(r"\b\d{1,3}(?:\.\d{3})*,\d{2}\b", texto_busca)
    if not valores:
        return None

    valor_texto = valores[-1]
    valor = moeda_para_decimal(valor_texto)
    if valor is None:
        return None

    descricao = texto_original
    descricao = re.sub(r"\b\d{1,3}(?:\.\d{3})*,\d{2}\b", "", descricao)
    descricao = re.sub(r"\b\d{2}/\d{2}\b", "", descricao, count=1)
    descricao = re.sub(r"\s+", " ", descricao).strip()

    return LancamentoFatura(
        data=data_match.group(1),
        descricao=descricao[:140],
        valor_texto=valor_texto,
        valor=valor,
        localizador=extrair_localizador(texto_busca),
        bruto_texto=texto_original,
    )


def extrair_lancamentos_fatura(texto_fatura: str, nome_titular: str) -> List[LancamentoFatura]:
    secao = localizar_secao_titular(texto_fatura, nome_titular)
    if not secao:
        secao = localizar_secao_santander(texto_fatura, nome_titular)
    if not secao:
        return []

    linhas = secao.splitlines()
    if linhas:
        linhas = linhas[1:]

    if any("TRANSACOES NACIONAIS" in ascii_fold(l) for l in linhas):
        lancamentos = []
        padrao = re.compile(
            r"^(\d{2}-\d{2}-\d{4})\s+(.+?)\s+(-?\d[\d\.,]*)\s*$",
            re.IGNORECASE,
        )
        for linha in linhas:
            linha_busca = ascii_fold(linha)
            if linha_busca.startswith("TOTAL EM R$"):
                break
            if linha_busca.startswith("TRANSACOES") or not re.match(r"^\d{2}-\d{2}-\d{4}", linha_busca):
                continue

            match = padrao.match(linha_busca)
            if not match:
                # tenta capturar linhas com espaços estranhos no fim
                alt = re.match(r"^(\d{2}-\d{2}-\d{4})\s+(.+?)\s+(-?\d[\d\.,]*)\s*$", linha_busca)
                if not alt:
                    continue
                match = alt

            valor_texto = match.group(3).replace(" ", "")
            valor_base = moeda_para_decimal(valor_texto.replace("-", "").strip())
            if valor_base is None:
                continue
            valor = -valor_base if valor_texto.startswith("-") else valor_base
            descricao = re.sub(r"\s+", " ", match.group(2)).strip()
            lancamentos.append(
                LancamentoFatura(
                    data=match.group(1).replace("-", "/")[:5],
                    descricao=descricao[:140],
                    valor_texto=valor_texto,
                    valor=valor.copy_abs(),
                    localizador=extrair_localizador(linha_busca),
                    bruto_texto=linha,
                )
            )
        return lancamentos

    blocos = agrupar_blocos_transacao(linhas)
    lancamentos = []
    for bloco in blocos:
        lancamento = extrair_lancamento_bloco(bloco)
        if lancamento:
            lancamentos.append(lancamento)
    return lancamentos


def extrair_referencia_hospedagem(texto: str, arquivo: str) -> List[ReferenciaPedido]:
    itens = []

    texto_busca = ascii_fold(texto)
    padrao = re.compile(
        r"(?:CARTAO|FATURADO)\s+"
        r"(.*?)\s+"
        r"(\d{2}/\d{2}(?:/\d{2,4})?)\s+"
        r"(\d{2}/\d{2}(?:/\d{2,4})?)\s+"
        r"(\d+)\s+"
        r"R\$\s*([\d\.,]+)\s+"
        r"R\$\s*([\d\.,]+)\s+"
        r"R\$\s*([\d\.,]+)\s+"
        r"(\d{4,7})",
        re.IGNORECASE | re.DOTALL,
    )

    for match in padrao.finditer(texto_busca):
        descricao = re.sub(r"\s+", " ", match.group(1)).strip()
        if "FUNCIONARIO HOTEL CIDADE" in descricao[:80]:
            continue

        valor_texto = match.group(7)
        valor = moeda_para_decimal(valor_texto)
        if valor is None:
            continue

        restante = texto_busca[match.end(7) :]
        intine = None
        pedido = None
        intine_match = re.search(r"\b(\d{10,15})\b\s+(\d{4,7})\b", restante)
        if intine_match:
            intine = intine_match.group(1)
            pedido = intine_match.group(2)
        else:
            intine_match = re.search(r"\b(\d{10,15})\b", restante)
            if intine_match:
                intine = intine_match.group(1)

            pedidos = re.findall(r"\b(\d{4,7})\b", restante)
            if pedidos:
                pedido = pedidos[-1]

        if not pedido:
            continue

        itens.append(
            ReferenciaPedido(
                origem_arquivo=arquivo,
                origem_tipo="hospedagem",
                pedido=pedido,
                valor_texto=valor_texto,
                valor=valor,
                descricao=descricao[:180],
                datas=[normalizar_data(match.group(2)), normalizar_data(match.group(3))],
                intine=intine,
            )
        )

    return itens


def extrair_referencia_portal(texto: str, arquivo: str) -> List[ReferenciaPedido]:
    texto_busca = ascii_fold(texto)
    padrao = re.compile(
        r"\b([A-Z0-9]{6})\b.*?\b(\d{4,7})\b.*?R\$\s*([\d\.,]+)",
        re.IGNORECASE,
    )
    itens = []

    for match in padrao.finditer(texto_busca):
        valor = moeda_para_decimal(match.group(3))
        if valor is None:
            continue

        itens.append(
            ReferenciaPedido(
                origem_arquivo=arquivo,
                origem_tipo="portal",
                pedido=match.group(2),
                valor_texto=match.group(3),
                valor=valor,
                descricao=match.group(0)[:180],
                localizador=match.group(1).upper(),
            )
        )

    return itens


def extrair_referencias_arquivo(nome_arquivo: str, conteudo_bytes: bytes) -> List[ReferenciaPedido]:
    texto = ler_pdf_bytes(conteudo_bytes)
    if not texto.strip():
        return []

    itens = extrair_referencia_hospedagem(texto, nome_arquivo)
    if itens:
        return itens

    return extrair_referencia_portal(texto, nome_arquivo)


def pontuar_correspondencia(lancamento: LancamentoFatura, referencia: ReferenciaPedido) -> Decimal:
    score = Decimal("0")

    if lancamento.localizador and referencia.localizador and lancamento.localizador == referencia.localizador:
        score += Decimal("100")

    diff = abs(lancamento.valor - referencia.valor)
    if diff == Decimal("0"):
        score += Decimal("50")
    elif diff <= TOLERANCIA_VALOR:
        score += Decimal("30")

    data_lancamento = normalizar_data(lancamento.data)
    datas_ref = {normalizar_data(d) for d in referencia.datas if d}
    if data_lancamento and data_lancamento in datas_ref:
        score += Decimal("20")

    return score


def lancamento_e_estorno(lancamento: LancamentoFatura) -> bool:
    bruto = ascii_fold(lancamento.bruto_texto)
    if "-" in lancamento.bruto_texto:
        if re.search(r"-\s*(?:R\$)?\s*%s\b" % re.escape(lancamento.valor_texto), bruto):
            return True
    if "ESTORNO" in bruto or "CANCEL" in bruto:
        return True
    return False


def conciliar_lancamentos(
    lancamentos: List[LancamentoFatura],
    referencias: List[ReferenciaPedido],
) -> List[Dict[str, str]]:
    resultado = []

    for lancamento in lancamentos:
        if lancamento_e_estorno(lancamento):
            resultado.append(
                {
                    "Data": lancamento.data,
                    "Descricao": lancamento.descricao,
                    "Localizador": lancamento.localizador or "",
                    "Valor": lancamento.valor_texto,
                    "Pedido": "ESTORNO",
                    "Status": "ESTORNO",
                    "Criterio": "ESTORNO",
                    "Origem": "ESTORNO",
                    "Tipo": "ESTORNO",
                }
            )
            continue

        candidatos = []
        for ref in referencias:
            if abs(lancamento.valor - ref.valor) <= TOLERANCIA_VALOR:
                candidatos.append(ref)

        escolhido = None
        criterio = ""
        status = "PENDENTE"
        pedido_extra = ""

        if candidatos:
            pontuados = []
            for ref in candidatos:
                score = pontuar_correspondencia(lancamento, ref)
                pontuados.append((score, ref))

            pontuados.sort(key=lambda item: (item[0], item[1].pedido), reverse=True)
            melhor_score, melhor_ref = pontuados[0]
            empatados = [item for item in pontuados if item[0] == melhor_score]

            if len(empatados) == 1 and melhor_score > 0:
                escolhido = melhor_ref
                if lancamento.localizador and melhor_ref.localizador and lancamento.localizador == melhor_ref.localizador:
                    criterio = "Localizador"
                elif normalizar_data(lancamento.data) in {normalizar_data(d) for d in melhor_ref.datas if d}:
                    criterio = "Valor + Data"
                else:
                    criterio = "Valor"
                status = "OK"
            elif len(empatados) == 1:
                escolhido = melhor_ref
                criterio = "Valor"
                status = "OK"
            else:
                status = "AMBIGUO"
                criterio = "Valor duplicado"
                pedido_extra = ", ".join(sorted({item[1].pedido for item in empatados}))

        pedido = escolhido.pedido if escolhido else ""
        origem = escolhido.origem_arquivo if escolhido else ""
        origem_tipo = escolhido.origem_tipo if escolhido else ""
        if status == "AMBIGUO" and pedido_extra:
            pedido = pedido_extra

        resultado.append(
            {
                "Data": lancamento.data,
                "Descricao": lancamento.descricao,
                "Localizador": lancamento.localizador or "",
                "Valor": lancamento.valor_texto,
                "Pedido": pedido or status,
                "Status": status,
                "Criterio": criterio,
                "Origem": origem,
                "Tipo": origem_tipo,
            }
        )

    return resultado


def gerar_excel(resultado: List[Dict[str, str]]) -> bytes:
    df = pd.DataFrame(resultado)
    saida = io.BytesIO()
    with pd.ExcelWriter(saida, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Conciliacao")
    return saida.getvalue()


def gerar_csv(resultado: List[Dict[str, str]]) -> bytes:
    df = pd.DataFrame(resultado)
    return df.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig")


def gerar_pdf(resultado: List[Dict[str, str]]) -> bytes:
    if FPDF is None:
        return b""

    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=10)
    pdf.add_page()

    pdf.set_font("Arial", "B", 13)
    pdf.cell(0, 8, "Relatorio de Conciliacao", ln=True, align="C")
    pdf.ln(2)

    colunas = [
        ("Data", 20),
        ("Descricao", 96),
        ("Localizador", 24),
        ("Valor", 24),
        ("Pedido", 28),
        ("Status", 20),
        ("Criterio", 30),
        ("Origem", 40),
    ]

    pdf.set_font("Arial", "B", 8)
    pdf.set_fill_color(230, 230, 230)
    for titulo, largura in colunas:
        pdf.cell(largura, 7, titulo, 1, 0, "C", True)
    pdf.ln()

    pdf.set_font("Arial", "", 8)
    for linha in resultado:
        status = linha["Status"]
        if status == "PENDENTE":
            pdf.set_text_color(200, 0, 0)
        elif status == "AMBIGUO":
            pdf.set_text_color(180, 110, 0)
        else:
            pdf.set_text_color(0, 0, 0)

        valores = [
            linha["Data"],
            linha["Descricao"],
            linha["Localizador"],
            linha["Valor"],
            linha["Pedido"],
            linha["Status"],
            linha["Criterio"],
            linha["Origem"],
        ]

        for (titulo, largura), valor in zip(colunas, valores):
            texto = ascii_fold(str(valor))[:80]
            pdf.cell(largura, 7, texto, 1)
        pdf.ln()

    pdf.set_text_color(0, 0, 0)
    return pdf.output(dest="S").encode("latin-1", "replace")


def classe_linha(status: str) -> str:
    if status == "ESTORNO":
        return "row-estorno"
    if status == "PENDENTE":
        return "row-pendente"
    if status == "AMBIGUO":
        return "row-duplicado"
    return "row-ok"


def chip_status(status: str) -> str:
    if status == "ESTORNO":
        return '<span class="chip chip-estorno">ESTORNO</span>'
    if status == "PENDENTE":
        return '<span class="chip chip-pendente">PENDENTE</span>'
    if status == "AMBIGUO":
        return '<span class="chip chip-duplicado">DUPLICADO</span>'
    return '<span class="chip chip-ok">OK</span>'


def render_table_html(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    html = ['<div class="table-wrap">', '<table class="mse-table">', '<thead><tr>']
    for col in cols:
        html.append(f"<th>{col}</th>")
    html.append("</tr></thead><tbody>")

    for _, row in df.iterrows():
        status = str(row.get("Status", ""))
        html.append(f'<tr class="{classe_linha(status)}">')
        for col in cols:
            value = row.get(col, "")
            if col == "Status":
                value = chip_status(str(value))
            else:
                value = str(value)
            html.append(f"<td>{value}</td>")
        html.append("</tr>")

    html.append("</tbody></table></div>")
    return "".join(html)


def resumo_html(df: pd.DataFrame) -> str:
    total = len(df)
    estornos = int((df["Status"] == "ESTORNO").sum()) if total else 0
    pendentes = int((df["Status"] == "PENDENTE").sum()) if total else 0
    ambiguos = int((df["Status"] == "AMBIGUO").sum()) if total else 0
    ok = int((df["Status"] == "OK").sum()) if total else 0
    return f"""
    <div class="summary-row">
        <div class="summary-card"><div class="summary-label">Processados</div><div class="summary-value">{total}</div></div>
        <div class="summary-card"><div class="summary-label">OK</div><div class="summary-value">{ok}</div></div>
        <div class="summary-card"><div class="summary-label">Estornos</div><div class="summary-value">{estornos}</div></div>
        <div class="summary-card"><div class="summary-label">Pendentes</div><div class="summary-value">{pendentes}</div></div>
        <div class="summary-card"><div class="summary-label">Duplicados</div><div class="summary-value">{ambiguos}</div></div>
    </div>
    """


def nome_arquivo_saida(nome: str, extensao: str) -> str:
    base = ascii_fold(nome).replace(" ", "_")
    base = re.sub(r"[^A-Z0-9_]+", "", base)
    return f"Conciliacao_{base}.{extensao}"


st.markdown(CSS_APP, unsafe_allow_html=True)

st.markdown(
    """
    <div class="mse-topbar">
        <div class="mse-brand">
            <span style="width:12px;height:12px;border-radius:999px;background:var(--mse);display:inline-block"></span>
            <span>Modelo App Script - <span style="color:#e91e4f;">Conciliador Faturas</span></span>
        </div>
        <div class="small-muted">MSE Portal</div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="app-title">Conciliador de Cartao</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="app-subtitle">Envie a fatura e os arquivos de apoio para extrair os lancamentos e cruzar os valores.</div>',
    unsafe_allow_html=True,
)

st.markdown('<div class="panel"><div class="panel-title">Arquivos</div>', unsafe_allow_html=True)
st.markdown('<div class="upload-label">Fatura em PDF</div>', unsafe_allow_html=True)
arquivo_fatura = st.file_uploader("", type=["pdf"], key="fatura", label_visibility="collapsed")
st.markdown('<div class="upload-label" style="margin-top:12px;">Planilhas/relatorios em PDF</div>', unsafe_allow_html=True)
arquivos_ref = st.file_uploader(
    "", type=["pdf"], accept_multiple_files=True, key="refs", label_visibility="collapsed"
)
st.markdown('</div>', unsafe_allow_html=True)

if arquivo_fatura:
    texto_fatura = ler_pdf_bytes(arquivo_fatura.getvalue())
    titulares = detectar_titulares(texto_fatura)

    st.markdown('<div class="panel"><div class="panel-title">Selecionar titular</div>', unsafe_allow_html=True)
    if titulares:
        titular = st.selectbox("", titulares, label_visibility="collapsed")
    else:
        titular = st.text_input("", value="ARIANI DE SOUZA", label_visibility="collapsed")

    botao = st.button("Processar")
    st.markdown('</div>', unsafe_allow_html=True)

    if botao:
        lancamentos = extrair_lancamentos_fatura(texto_fatura, titular)

        referencias = []
        if arquivos_ref:
            for arquivo in arquivos_ref:
                referencias.extend(
                    extrair_referencias_arquivo(arquivo.name, arquivo.getvalue())
                )

        if not lancamentos:
            st.error("Nao foi possivel extrair lancamentos da fatura para esse titular.")
            st.stop()

        if not referencias:
            st.warning(
                "Nao consegui extrair referencias dos PDFs enviados. Ainda assim, mostro os lancamentos da fatura."
            )

        resultado = conciliar_lancamentos(lancamentos, referencias) if referencias else []

        df_lancamentos = pd.DataFrame(
            [
                {
                    "Data": l.data,
                    "Descricao": l.descricao,
                    "Localizador": l.localizador or "",
                    "Valor": l.valor_texto,
                }
                for l in lancamentos
            ]
        )
        st.markdown('<div class="panel"><div class="panel-title">Lancamentos da fatura</div>', unsafe_allow_html=True)
        st.markdown(resumo_html(df_lancamentos), unsafe_allow_html=True)
        st.markdown(render_table_html(df_lancamentos), unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

        if resultado:
            df_resultado = pd.DataFrame(resultado)
            st.markdown('<div class="panel"><div class="panel-title">Conciliacao</div>', unsafe_allow_html=True)
            st.markdown(resumo_html(df_resultado), unsafe_allow_html=True)
            st.markdown(render_table_html(df_resultado), unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

            pdf_bytes = gerar_pdf(resultado)
            xlsx_bytes = gerar_excel(resultado)
            csv_bytes = gerar_csv(resultado)

            if pdf_bytes:
                st.download_button(
                    "Baixar PDF",
                    data=pdf_bytes,
                    file_name=nome_arquivo_saida(titular, "pdf"),
                    mime="application/pdf",
                )
            else:
                st.warning("Biblioteca fpdf nao encontrada. O PDF de saida foi desativado.")

            st.download_button(
                "Baixar Excel",
                data=xlsx_bytes,
                file_name=nome_arquivo_saida(titular, "xlsx"),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            st.download_button(
                "Baixar CSV",
                data=csv_bytes,
                file_name=nome_arquivo_saida(titular, "csv"),
                mime="text/csv",
            )
        else:
            st.warning("Nao houve referencias suficientes para fazer a conciliacao.")

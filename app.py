import pypdf
import pandas as pd
import re
import io
import streamlit as st
from fpdf import FPDF

def ler_pdf_bytes(conteudo_bytes):
    text = ""
    try:
        reader = pypdf.PdfReader(io.BytesIO(conteudo_bytes))
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        st.error(f"Erro ao ler PDF: {e}")
        return ""

st.set_page_config(page_title="Conciliador Inteligente", page_icon="📊", layout="centered")

st.title("📊 Conciliador Inteligente de Pedidos")
st.markdown("Faça o upload da sua **Fatura** e do documento **Info** para cruzar os dados automaticamente.")

arquivo_fatura = st.file_uploader("1. Selecione o arquivo de Fatura (PDF)", type=["pdf"])
arquivo_info = st.file_uploader("2. Selecione o arquivo Info (PDF)", type=["pdf"])

if st.button("Iniciar Conciliação ⏳"):
    if not arquivo_fatura or not arquivo_info:
        st.warning("⚠️ Por favor, envie ambos os arquivos para continuar.")
    else:
        with st.spinner("Processando os dados..."):
            txt_fatura = ler_pdf_bytes(arquivo_fatura.read())
            txt_info = ler_pdf_bytes(arquivo_info.read())

            pedidos_portal = []
            padrao_info = re.compile(r'([A-Z0-9]{6})\s+[A-Z\s]+\s+(\d{4,7})\s+R\$\s*([\d\.,]+)')
            for m in padrao_info.finditer(txt_info):
                pedidos_portal.append({
                    "Loc": m.group(1),
                    "Pedido": m.group(2),
                    "Valor": m.group(3).strip()
                })

            padrao_nome = re.compile(r'ARIANI.*?SOUZA', re.IGNORECASE)
            match_nome = padrao_nome.search(txt_fatura)
            
            final_dados = []

            if match_nome:
                inicio = match_nome.start()
                texto_ariani = txt_fatura[inicio:]
                linhas = texto_ariani.split('\n')
                
                for linha in linhas:
                    if "Total para" in linha or ("Cartão" in linha and "ARIANI" not in linha.upper()):
                        break
                    
                    data_m = re.search(r'(\d{2}/\d{2})', linha)
                    valor_m = re.search(r'(\d{1,3}(?:\.\d{3})*,\d{2})', linha)
                    
                    if data_m and valor_m:
                        loc_m = re.search(r'\b([A-Z0-9]{6})\b', linha)
                        loc_fatura = loc_m.group(1) if loc_m else None
                        valor_fatura = valor_m.group(1)
                        
                        pedido_encontrado = "PENDENTE"
                        for p in pedidos_portal:
                            if (loc_fatura and loc_fatura == p['Loc']) or (valor_fatura == p['Valor']):
                                pedido_encontrado = p['Pedido']
                                break
                        
                        final_dados.append([data_m.group(1), linha.strip()[:35], valor_fatura, pedido_encontrado])
            
            if final_dados:
                st.success(f"✅ Sucesso! {len(final_dados)} itens processados.")
                
                df_visualizacao = pd.DataFrame(final_dados, columns=["Data", "Descrição", "Valor", "Pedido"])
                st.dataframe(df_visualizacao, use_container_width=True)
                
                pdf = FPDF()
                pdf.add_page()
                pdf.set_font("Arial", "B", 16)
                pdf.cell(190, 10, "Relatorio de Conciliacao Ariani", ln=True, align='C')
                pdf.ln(10)

                pdf.set_font("Arial", "B", 10)
                pdf.set_fill_color(230, 230, 230)
                pdf.cell(25, 10, "Data", 1, 0, 'C', True)
                pdf.cell(75, 10, "Descricao", 1, 0, 'C', True)
                pdf.cell(40, 10, "Valor", 1, 0, 'C', True)
                pdf.cell(50, 10, "Pedido", 1, 1, 'C', True)

                for r in final_dados:
                    pdf.set_font("Arial", "", 9)
                    pdf.cell(25, 10, r[0], 1)
                    pdf.cell(75, 10, r[1], 1)
                    pdf.cell(40, 10, r[2], 1)
                    if r[3] == "PENDENTE":
                        pdf.set_text_color(255, 0, 0)
                    pdf.cell(50, 10, r[3], 1, 1)
                    pdf.set_text_color(0, 0, 0)

                pdf_output = pdf.output(dest='S').encode('latin1')
                
                st.download_button(
                    label="📥 Baixar Relatório (PDF)",
                    data=pdf_output,
                    file_name="Resultado_Final.pdf",
                    mime="application/pdf"
                )
            else:
                st.error("❌ Nenhuma transação encontrada. Verifique se o nome Ariani está no PDF da fatura.")

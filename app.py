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

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Conciliador por Funcionário", page_icon="💳", layout="centered")

st.title("💳 Conciliador de Cartão por Funcionário")
st.markdown("Faça o upload da Fatura e do Relatório de Viagens para conciliar seus pedidos.")

# Upload dos arquivos
arquivo_fatura = st.file_uploader("1. Faça o upload da Fatura do Cartão (PDF)", type=["pdf"])
arquivo_viagens = st.file_uploader("2. Faça o upload do Relatório de Viagens/Pedidos (PDF)", type=["pdf"])

if arquivo_fatura and arquivo_viagens:
    
    # Armazena os textos na sessão para não precisar ler o PDF toda vez que mudar o nome
    if "txt_fatura" not in st.session_state:
        with st.spinner("Lendo e interpretando os PDFs..."):
            st.session_state.txt_fatura = ler_pdf_bytes(arquivo_fatura.read())
            st.session_state.txt_viagens = ler_pdf_bytes(arquivo_viagens.read())
            
    txt_fatura = st.session_state.txt_fatura
    txt_viagens = st.session_state.txt_viagens

    # --- 1. DETECTAR OS NOME DISPONÍVEIS NA FATURA ---
    # Busca pelo padrão de fechamento de blocos da fatura: "Total para NOME" ou "para NOME Total"
    nomes_fatura = sorted(list(set(re.findall(r'(?:Total\s+para|para)\s+([A-Z\s]{4,30})', txt_fatura, re.IGNORECASE))))
    nomes_limpos = [nome.strip().upper() for nome in nomes_fatura if len(nome.strip()) > 3]

    if not nomes_limpos:
        st.error("❌ Não conseguimos identificar os nomes dos funcionários na fatura. Verifique o arquivo.")
    else:
        # Interface para o usuário escolher quem ele é
        nome_selecionado = st.selectbox("👤 Quem é você? Selecione seu nome:", ["Clique para selecionar..."] + nomes_limpos)

        if nome_selecionado != "Clique para selecionar...":
            
            # --- 2. EXTRAIR APENAS O TRECHO DA FATURA DA PESSOA SELECIONADA ---
            # Encontra onde começa o bloco da pessoa e onde termina
            linhas_fatura = txt_fatura.split("\n")
            linhas_da_pessoa = []
            capturando = False
            
            # Pega o primeiro nome (geralmente só o primeiro nome ou sobrenome para o match flexível)
            primeiro_nome = nome_selecionado.split()[0]
            
            for linha in linhas_fatura:
                # Se achar o nome do funcionário isolado ou iniciando bloco, começa a capturar
                if primeiro_nome in linha.upper() and ("CARTÃO" in linha.upper() or len(linha.strip()) < 40):
                    capturando = True
                
                if capturando:
                    linhas_da_pessoa.append(linha)
                    
                # Se chegar no "Total para" daquela pessoa, encerra a captura do bloco dela
                if "TOTAL" in linha.upper() and primeiro_nome in linha.upper():
                    capturando = False
                    break

            texto_filtrado_fatura = "\n".join(linhas_da_pessoa)

            # --- 3. MAPEANDO PEDIDOS DO RELATÓRIO DE VIAGENS ---
            # Lê o documento de viagens linha por linha buscando Localizadores, Pedidos e Valores
            pedidos_viagens = []
            linhas_v = txt_viagens.split("\n")
            
            for lv in lines_v:
                # Procura por padrões de Localizadores (6 dígitos alfanuméricos)
                loc_m = re.search(r'\b([A-Z0-9]{6})\b', lv)
                # Procura por valores em R$
                valor_m = re.search(r'R\$\s*([\d\.,]+)', lv)
                # Procura por números de pedido (geralmente de 4 a 7 dígitos)
                pedido_m = re.search(r'\b(\d{4,7})\b', lv)
                
                if valor_m:
                    pedidos_viagens.append({
                        "Loc": loc_m.group(1) if loc_m else None,
                        "Pedido": pedido_m.group(1) if pedido_m else "N/A",
                        "Valor": valor_m.group(1).strip()
                    })

            # --- 4. PROCESSANDO OS LANÇAMENTOS EXCLUSIVOS DA PESSOA ---
            final_dados = []
            
            for linha in linhas_da_pessoa:
                # Ignora linhas de totalizadores ou cabeçalhos do bloco
                if "TOTAL" in linha.upper() or "CARTÃO" in linha.upper():
                    continue
                    
                data_m = re.search(r'(\d{2}/\d{2})', linha)
                valor_m = re.search(r'(\d{1,3}(?:\.\d{3})*,\d{2})', linha)
                
                if data_m and valor_m:
                    loc_m = re.search(r'\b([A-Z0-9]{6})\b', linha)
                    loc_fatura = loc_m.group(1) if loc_m else None
                    valor_fatura = valor_m.group(1)
                    
                    # Tenta descobrir o termo de descrição (Ex: Azul Linhas, Expedia, etc)
                    descricao = linha.strip()[:40]
                    
                    pedido_encontrado = "PENDENTE"
                    
                    # Cruzamento inteligente: tenta por localizador ou por valor exato
                    for p in pedidos_viagens:
                        if (loc_fatura and loc_fatura == p['Loc']) or (valor_fatura == p['Valor']):
                            pedido_encontrado = p['Pedido']
                            break
                    
                    final_dados.append([data_m.group(1), descricao, valor_fatura, pedido_encontrado])

            # --- 5. EXIBIÇÃO DOS RESULTADOS ---
            st.write(f"### 📋 Lançamentos encontrados para: **{nome_selecionado}**")
            
            if final_dados:
                df_visualizacao = pd.DataFrame(final_dados, columns=["Data", "Descrição da Fatura", "Valor", "Nº Pedido Encontrado"])
                
                # Destaca linhas pendentes em vermelho na tabela visual
                st.dataframe(df_visualizacao, use_container_width=True)
                
                # --- GERADOR DO PDF DE SAÍDA ---
                pdf = FPDF()
                pdf.add_page()
                pdf.set_font("Arial", "B", 14)
                pdf.cell(190, 10, f"Relatorio de Conciliacao - {nome_selecionado}", ln=True, align='C')
                pdf.ln(5)

                # Cabeçalho da tabela no PDF
                pdf.set_font("Arial", "B", 10)
                pdf.set_fill_color(230, 230, 230)
                pdf.cell(20, 10, "Data", 1, 0, 'C', True)
                pdf.cell(85, 10, "Descricao Fatura", 1, 0, 'L', True)
                pdf.cell(35, 10, "Valor", 1, 0, 'C', True)
                pdf.cell(50, 10, "Numero Pedido", 1, 1, 'C', True)

                # Conteúdo da tabela no PDF
                pdf.set_font("Arial", "", 9)
                for r in final_dados:
                    pdf.cell(20, 10, r[0], 1, 0, 'C')
                    pdf.cell(85, 10, r[1][:45], 1, 0, 'L')
                    pdf.cell(35, 10, r[2], 1, 0, 'C')
                    
                    if r[3] == "PENDENTE":
                        pdf.set_text_color(255, 0, 0) # Texto vermelho se não achar o pedido
                    
                    pdf.cell(50, 10, r[3], 1, 1, 'C')
                    pdf.set_text_color(0, 0, 0) # Reseta cor

                pdf_output = pdf.output(dest='S').encode('latin1')
                
                st.ln(2)
                st.download_button(
                    label=f"📥 Baixar Relatório de {nome_selecionado} (PDF)",
                    data=pdf_output,
                    file_name=f"Conciliacao_{nome_selecionado.replace(' ', '_')}.pdf",
                    mime="application/pdf"
                )
            else:
                st.warning("Nenhum lançamento de compras com formato Data + Valor foi localizado no seu bloco da fatura.")

else:
    # Reseta a sessão se os arquivos forem removidos
    if "txt_fatura" in st.session_state:
        del st.session_state.txt_fatura
    if "txt_viagens" in st.session_state:
        del st.session_state.txt_viagens

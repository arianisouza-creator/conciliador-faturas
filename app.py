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



def limpar_valor(valor_str):

    if not valor_str:

        return 0.0

    dado_limpo = re.sub(r'[^\d,.]', '', valor_str)

    if ',' in dado_limpo and '.' in dado_limpo:

        dado_limpo = dado_limpo.replace('.', '').replace(',', '.')

    elif ',' in dado_limpo:

        dado_limpo = dado_limpo.replace(',', '.')

    try:

        return float(dado_limpo)

    except:

        return 0.0



# --- CONFIGURAÇÃO DA PÁGINA ---

st.set_page_config(page_title="Conciliador Universal", page_icon="💳", layout="centered")



st.title("💳 Conciliador de Cartão por Funcionário")

st.markdown("Faça o upload da Fatura e de qualquer Relatório/Planilha em PDF para conciliar.")



arquivo_fatura = st.file_uploader("1. Faça o upload da Fatura do Cartão (PDF)", type=["pdf"])

arquivos_viagens = st.file_uploader(

    "2. Faça o upload dos Relatórios de Pedidos / Planilhas (PDF)", 

    type=["pdf"], 

    accept_multiple_files=True

)



if arquivo_fatura and arquivos_viagens:

    

    txt_fatura = ler_pdf_bytes(arquivo_fatura.getvalue())

    

    txt_viagens_consolidado = ""

    for arq_viagem in arquivos_viagens:

        txt_viagens_consolidado += ler_pdf_bytes(arq_viagem.getvalue()) + "\n"



    # --- 1. DETECTAR OS NOMES DISPONÍVEIS NA FATURA ---

    nomes_fatura = sorted(list(set(re.findall(r'(?:Total\s+para|para)\s+([A-Z\s]{4,30})', txt_fatura, re.IGNORECASE))))

    nomes_limpos = [nome.strip().upper() for nome in nomes_fatura if len(nome.strip()) > 3]



    if not nomes_limpos:

        st.error("❌ Não conseguimos identificar os nomes dos funcionários na fatura. Verifique o arquivo.")

    else:

        nome_selecionado = st.selectbox("👤 Quem é você? Selecione seu nome:", ["Clique para selecionar..."] + nomes_limpos)



        if nome_selecionado != "Clique para selecionar...":

            

            # --- 2. EXTRAIR APENAS O TRECHO DA FATURA DA PESSOA SELECIONADA ---

            linhas_fatura = txt_fatura.split("\n")

            linhas_da_pessoa = []

            capturando = False

            

            primeiro_nome = nome_selecionado.split()[0]

            

            for linha in linhas_fatura:

                if primeiro_nome in linha.upper() and ("CARTÃO" in linha.upper() or len(linha.strip()) < 40):

                    capturando = True

                

                if capturando:

                    linhas_da_pessoa.append(linha)

                    

                if "TOTAL" in linha.upper() and primeiro_nome in linha.upper():

                    capturando = False

                    break



            # --- 3. MAPEAMENTO INTELIGENTE (VALOR + PEDIDO SEM PEGAR O ANO) ---

            banco_de_dados_viagens = []

            linhas_v = txt_viagens_consolidado.split("\n")

            

            ultimo_pedido_valido = "N/A"

            ultimo_loc_valido = None

            

            for lv in linhas_v:

                loc_m = re.search(r'\b([A-Z0-9]{6})\b', lv)

                if loc_m and not loc_m.group(1).isdigit(): 

                    ultimo_loc_valido = loc_m.group(1)

                

                todos_numeros = re.findall(r'\b(\d{4,7})\b', lv)

                for num in todos_numeros:

                    if num in ["2025", "2026", "2027", "0226"]:

                        continue

                    else:

                        ultimo_pedido_valido = num

                        break

                

                valor_m = re.search(r'R\$\s*([\d\.,\s]+)', lv)

                if valor_m:

                    v_texto = valor_m.group(1).strip()

                    valores_capturados = [v.strip() for v in re.split(r'\s+', v_texto) if v.strip()]

                    

                    for v_individual in valores_capturados:

                        v_puro = limpar_valor(v_individual)

                        if v_puro > 0:

                            banco_de_dados_viagens.append({

                                "Loc": ultimo_loc_valido,

                                "Pedido": ultimo_pedido_valido,

                                "ValorPuro": v_puro

                            })

            

            # --- 4. PROCESSANDO OS LANÇAMENTOS EXCLUSIVOS DA PESSOA ---

            final_dados = []

            

            for linha in linhas_da_pessoa:

                if "TOTAL" in linha.upper() or "CARTÃO" in linha.upper():

                    continue

                    

                data_m = re.search(r'(\d{2}/\d{2})', linha)

                valores_na_linha = re.findall(r'(\d{1,3}(?:\.\d{3})*,\d{1,2})', linha)

                

                if data_m and valores_na_linha:

                    valor_fatura = max(valores_na_linha, key=len)

                    valor_fatura_puro = limpar_valor(valor_fatura)

                    

                    loc_m = re.search(r'\b([A-Z0-9]{6})\b', linha)

                    loc_fatura = loc_m.group(1) if loc_m else None

                    

                    descricao = linha.strip()[:40]

                    pedido_encontrado = "PENDENTE"

                    

                    for p in banco_de_dados_viagens:

                        if (loc_fatura and p['Loc'] and loc_fatura == p['Loc']) or (abs(valor_fatura_puro - p['ValorPuro']) < 0.20):

                            pedido_encontrado = p['Pedido']

                            break

                    

                    valor_exibicao = valor_fatura if ',' in valor_fatura and len(valor_fatura.split(',')[1]) == 2 else f"{valor_fatura}0"

                    final_dados.append([data_m.group(1), descricao, valor_exibicao, pedido_encontrado])



            # --- 5. EXIBIÇÃO DOS RESULTADOS ---

            st.write(f"### 📋 Lançamentos encontrados para: **{nome_selecionado}**")

            

            if final_dados:

                df_visualizacao = pd.DataFrame(final_dados, columns=["Data", "Descrição da Fatura", "Valor", "Nº Pedido Encontrado"])

                st.table(df_visualizacao)

                

                # --- GERADOR DO PDF DE SAÍDA ---

                pdf = FPDF()

                pdf.add_page()

                pdf.set_font("Arial", "B", 14)

                pdf.cell(190, 10, f"Relatorio de Conciliacao - {nome_selecionado}", ln=True, align='C')

                pdf.ln(5)



                pdf.set_font("Arial", "B", 10)

                pdf.set_fill_color(230, 230, 230)

                pdf.cell(20, 10, "Data", 1, 0, 'C', True)

                pdf.cell(85, 10, "Descricao Fatura", 1, 0, 'L', True)

                pdf.cell(35, 10, "Valor", 1, 0, 'C', True)

                pdf.cell(50, 10, "Numero Pedido", 1, 1, 'C', True)



                pdf.set_font("Arial", "", 9)

                for r in final_dados:

                    pdf.cell(20, 10, r[0], 1, 0, 'C')

                    pdf.cell(85, 10, r[1][:45], 1, 0, 'L')

                    pdf.cell(35, 10, r[2], 1, 0, 'C')

                    if r[3] == "PENDENTE":

                        pdf.set_text_color(255, 0, 0)

                    pdf.cell(50, 10, r[3], 1, 1, 'C')

                    pdf.set_text_color(0, 0, 0)



                pdf_output = pdf.output(dest='S').encode('latin1')

                

                st.download_button(

                    label=f"📥 Baixar Relatório de {nome_selecionado} (PDF)",

                    data=pdf_output,

                    file_name=f"Conciliacao_{nome_selecionado.replace(' ', '_')}.pdf",

                    mime="application/pdf"

                )

            else:

                st.warning("Nenhum lançamento de compras válido foi localizado para este funcionário.") 


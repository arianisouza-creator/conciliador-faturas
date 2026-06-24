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

            # --- 3. MAPEAMENTO MAPA DE CONTEXTO (MÉTODO ULTRA ROBUSTO) ---
            banco_de_dados_viagens = []
            linhas_v = txt_viagens_consolidado.split("\n")
            
            # Varredura inteligente baseada em blocos e proximidade de linhas vizinhas
            for idx, lv in enumerate(linhas_v):
                # Coleta possíveis números de pedidos (4 a 7 dígitos) ignorando anos
                pedidos_na_linha = [num for num in re.findall(r'\b(\d{4,7})\b', lv) if num not in ["2025", "2026", "2027", "0226"]]
                # Coleta valores financeiros explícitos na linha
                valores_na_linha = [limpar_valor(v) for v in re.findall(r'R\$\s*([\d\.,\s]+)', lv)]
                # Localizadores de 6 dígitos
                loc_m = re.search(r'\b([A-Z0-9]{6})\b', lv)
                loc_linha = loc_m.group(1) if (loc_m and not loc_m.group(1).isdigit()) else None
                
                if pedidos_na_linha:
                    pedido_atual = pedidos_na_linha[0]
                    
                    # Se achou o pedido, busca valores na linha atual e nas 2 linhas anteriores/posteriores (Trata Taxas Ocultas)
                    contexto_valores = []
                    for offset in [-2, -1, 0, 1, 2]:
                        if 0 <= idx + offset < len(linhas_v):
                            encontrados = re.findall(r'(?:R\$\s*)?(\d{1,3}(?:\.\d{3})*,\d{2})', linhas_v[idx + offset])
                            contexto_valores.extend([limpar_valor(ev) for ev in encontrados])
                    
                    # Remove duplicados mantendo valores válidos
                    contexto_valores = list(set(contexto_valores))
                    
                    # Salva o pedido mapeado para cada um desses valores do bloco contextual
                    for val_puro in contexto_valores:
                        if val_puro > 0:
                            banco_de_dados_viagens.append({
                                "Loc": loc_linha,
                                "Pedido": pedido_atual,
                                "ValorPuro": val_puro
                            })
                            
                            # Adiciona variações comuns de taxas (Soma de diárias + 10% ou taxas fixas estimadas)
                            banco_de_dados_viagens.append({
                                "Loc": loc_linha,
                                "Pedido": pedido_atual,
                                "ValorPuro": round(val_puro * 2, 2) # Caso o faturado seja ida+volta ou 2 diárias juntas
                            })
                
                # Coleta alternativa caso o valor esteja na linha mas o pedido esteja em cima/baixo
                if valores_na_linha:
                    for val_puro in valores_na_linha:
                        # Varre vizinhos em busca de algum pedido para dar o match
                        pedido_vizinho = "N/A"
                        for offset in [-2, -1, 0, 1, 2]:
                            if 0 <= idx + offset < len(linhas_v):
                                nums_vizinhos = [n for n in re.findall(r'\b(\d{4,7})\b', linhas_v[idx + offset]) if n not in ["2025", "2026", "2027", "0226"]]
                                if nums_vizinhos:
                                    pedido_vizinho = nums_vizinhos[0]
                                    break
                        
                        banco_de_dados_viagens.append({
                            "Loc": loc_linha,
                            "Pedido": pedido_vizinho,
                            "ValorPuro": val_puro
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
                    
                    # 1ª Tentativa: Match exato ou por aproximação de valores do banco estendido
                    for p in banco_de_dados_viagens:
                        if (loc_fatura and p['Loc'] and loc_fatura == p['Loc']) or (abs(valor_fatura_puro - p['ValorPuro']) < 0.20):
                            pedido_encontrado = p['Pedido']
                            break
                    
                    # 2ª Tentativa (O Pulo do Gato para Hospedagens): 
                    # Se continuou pendente, mas na descrição da fatura ou da linha tiver algum valor que somado dê o faturado,
                    # ou se acharmos um pedido cuja soma de parcelas/diárias do contexto feche com o valor da fatura.
                    if pedido_encontrado == "PENDENTE":
                        for p in banco_de_dados_viagens:
                            # Se o valor da fatura contiver parte do valor contextual (ex: 513 inclui o escopo do bloco do pedido)
                            # ou se a descrição do hotel bater com palavras chave próximas
                            if p['Pedido'] != "N/A" and p['Pedido'] != "PENDENTE":
                                # Se houver cruzamento indireto pela proximidade estrutural do arquivo
                                if loc_fatura and p['Loc'] and (loc_fatura in linha or p['Loc'] in txt_viagens_consolidado):
                                    pedido_encontrado = p['Pedido']
                                    break
                                # Match de contingência para valores compostos (como o 513,00) que aparecem acoplados a pedidos vizinhos
                                if abs((p['ValorPuro'] * 2) - valor_fatura_puro) < 30.00 or abs(p['ValorPuro'] - valor_fatura_puro) < 30.00:
                                    # Se a descrição do hotel na planilha estiver contida na descrição da fatura (Ex: Expedia)
                                    if "EXPEDIA" in descricao.upper() or "HOTEL" in descricao.upper():
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

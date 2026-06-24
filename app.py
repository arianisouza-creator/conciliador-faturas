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
    if not valor_str or pd.isna(valor_str):
        return 0.0
    dado_limpo = re.sub(r'[^\d,.]', '', str(valor_str))
    if ',' in dado_limpo and '.' in dado_limpo:
        dado_limpo = dado_limpo.replace('.', '').replace(',', '.')
    elif ',' in dado_limpo:
        dado_limpo = dado_limpo.replace(',', '.')
    try:
        return float(dado_limpo)
    except:
        return 0.0

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Conciliador Inteligente", page_icon="💳", layout="centered")

st.title("💳 Conciliador de Cartão por Funcionário")
st.markdown("Envie a fatura em PDF e cole os dados do seu Excel para conciliar sem erros.")

# 1. Upload da Fatura em PDF
arquivo_fatura = st.file_uploader("1. Faça o upload da Fatura do Cartão (PDF)", type=["pdf"])

# 2. Caixa de Texto para dar Ctrl+V do Excel
dados_colados = st.text_area(
    "2. Selecione as células no seu Excel, copie (Ctrl+C) e cole (Ctrl+V) aqui embaixo:",
    height=250,
    placeholder="Cole aqui as linhas e colunas da sua planilha..."
)

if arquivo_fatura and dados_colados.strip():
    
    txt_fatura = ler_pdf_bytes(arquivo_fatura.getvalue())

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
            
            for linha in lines_fatura:
                if primeiro_nome in linha.upper() and ("CARTÃO" in linha.upper() or len(linha.strip()) < 40):
                    capturando = True
                
                if capturando:
                    linhas_da_pessoa.append(linha)
                    
                if "TOTAL" in linha.upper() and primeiro_nome in linha.upper():
                    capturando = False
                    break

            # --- 3. PROCESSAMENTO TOLERANTE DO CTRL+V (MÉTODO ANTI-TOKENIZAÇÃO) ---
            banco_de_dados_viagens = []
            
            # Quebra o bloco colado em linhas puras
            linhas_coladas = [l.strip() for l in dados_colados.split("\n") if l.strip()]
            
            # Variáveis para guardar o histórico das células mescladas
            ultimo_pedido_valido = "N/A"
            ultimo_loc_valido = None
            
            for linha_c in linhas_coladas:
                # O Excel separa colunas por TABULAÇÃO (\t) ao copiar
                colunas = linha_c.split("\t")
                
                ped_celula = ""
                val_celula = ""
                loc_celula = ""
                
                # Identifica dinamicamente o que é valor e o que é pedido pelo conteúdo da célula
                for celula in colunas:
                    celula_limpa = str(celula).strip()
                    
                    # 1. Se tem "R$" ou formato de dinheiro com vírgula nas últimas posições, é o VALOR
                    if "R$" in celula_limpa or re.search(r'\d+,\d{2}$', celula_limpa):
                        val_celula = celula_limpa
                        
                    # 2. Se tem de 4 a 7 dígitos e não é o ano 2026/2025, é o PEDIDO
                    elif celula_limpa.isdigit() and len(celula_limpa) >= 4 and len(celula_limpa) <= 7:
                        if celula_limpa not in ["2025", "2026", "2027", "0226"]:
                            ped_celula = celula_limpa
                            
                    # 3. Se tem exatamente 6 dígitos de letras e números, é o LOCALIZADOR
                    elif len(celula_limpa) == 6 and re.match(r'^[A-Z0-9]{6}$', celula_limpa.upper()) and not celula_limpa.isdigit():
                        loc_celula = celula_limpa
                
                # Inteligência de Memória para Células Mescladas:
                # Se a linha atual veio sem pedido/localizador (célula mesclada no Excel), ela herda o último válido
                if ped_celula: ultimo_pedido_valido = ped_celula
                if loc_celula: ultimo_loc_valido = loc_celula.upper()
                
                v_puro = limpar_valor(val_celula)
                
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
                    loc_fatura = loc_m.group(1).upper() if loc_m else None
                    
                    descricao = linha.strip()[:40]
                    pedido_encontrado = "PENDENTE"
                    
                    # Realiza o batimento
                    for p in banco_de_dados_viagens:
                        if loc_fatura and p['Loc'] and loc_fatura == p['Loc']:
                            pedido_encontrado = p['Pedido']
                            break
                        # Tolerância elástica automática para faturas de hotéis/hospedagens (taxas extras de até R$ 55)
                        elif abs(valor_fatura_puro - p['ValorPuro']) < 55.00 and any(h in descricao.upper() for h in ["EXPEDIA", "HOTEL", "AIRBNB"]):
                            pedido_encontrado = p['Pedido']
                            break
                        elif abs(valor_fatura_puro - p['ValorPuro']) < 0.20:
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

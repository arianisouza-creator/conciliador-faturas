import pypdf
import pdfplumber
import pandas as pd
import re
import io
import streamlit as st
from fpdf import FPDF

def ler_pdf_bytes(conteudo_bytes):
    """Lê a fatura (texto corrido)"""
    text = ""
    try:
        reader = pypdf.PdfReader(io.BytesIO(conteudo_bytes))
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        st.error(f"Erro ao ler PDF da fatura: {e}")
        return ""

def extrair_tabelas_reais(conteudo_bytes):
    """Lê as planilhas/relatórios usando inteligência de grade (pdfplumber) para células mescladas"""
    dados_mapeados = []
    try:
        with pdfplumber.open(io.BytesIO(conteudo_bytes)) as pdf:
            for pagina in pdf.pages:
                # Extrai a tabela respeitando linhas e colunas reais
                tabela = pagina.extract_table({
                    "vertical_strategy": "lines",
                    "horizontal_strategy": "lines",
                    "snap_tolerance": 3,
                })
                
                if not tabela:
                    # Tenta extração textual de contingência caso não haja linhas visíveis
                    tabela = pagina.extract_table()
                    
                if tabela:
                    df = pd.DataFrame(tabela)
                    # Remove linhas totalmente vazias
                    df.dropna(how='all', inplace=True)
                    dados_mapeados.append(df)
    except Exception as e:
        st.error(f"Erro ao processar estrutura da planilha: {e}")
    return dados_mapeados

def limpar_valor(valor_str):
    if not valor_str:
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
st.set_page_config(page_title="Conciliador de Precisão", page_icon="🧮", layout="centered")

st.title("🧮 Conciliador de Precisão Estruturado")
st.markdown("Sistema baseado em leitura de grades para prevenção de erros de cruzamento.")

arquivo_fatura = st.file_uploader("1. Faça o upload da Fatura do Cartão (PDF)", type=["pdf"])
arquivos_viagens = st.file_uploader(
    "2. Faça o upload das Planilhas / Relatórios de Pedidos (PDF)", 
    type=["pdf"], 
    accept_multiple_files=True
)

if arquivo_fatura and arquivos_viagens:
    
    txt_fatura = ler_pdf_bytes(arquivo_fatura.getvalue())
    
    # Processa todas as planilhas extraindo matrizes de tabelas reais
    tabelas_planilhas = []
    for arq_viagem in arquivos_viagens:
        tabelas_planilhas.extend(extrair_tabelas_reais(arq_viagem.getvalue()))

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

            # --- 3. PROCURAR COLUNAS DE VALOR E PEDIDO DINAMICAMENTE NAS MATRIZES ---
            banco_de_dados_viagens = []
            
            for df in tabelas_planilhas:
                col_pedido_idx = None
                col_valor_idx = None
                col_loc_idx = None
                
                # Passo 1: Descobrir o índice das colunas pelos cabeçalhos mapeados
                for linha_idx, linha in df.iterrows():
                    linha_txt = [str(celula).upper() for celula in linha]
                    
                    for idx, celula in enumerate(linha_txt):
                        if any(termo in celula for termo in ["PEDIDO", "INTINE", "SERVIÇO"]) and not col_pedido_idx:
                            col_pedido_idx = idx
                        if any(termo in celula for termo in ["VALOR", "TOTAL", "PAGO"]) and not col_valor_idx:
                            col_valor_idx = idx
                        if any(termo in celula for termo in ["LOCALIZADOR", "LOC"]) and not col_loc_idx:
                            col_loc_idx = idx
                            
                    if col_pedido_idx is not None or col_valor_idx is not None:
                        break # Achou o cabeçalho da tabela, pode começar a ler os dados abaixo
                
                # Se não achou cabeçalho claro, assume posições padrão (chute técnico seguro baseado nas colunas comuns)
                if col_valor_idx is None: col_valor_idx = df.shape[1] - 1 if df.shape[1] > 0 else 0
                if col_pedido_idx is None: col_pedido_idx = df.shape[1] - 2 if df.shape[1] > 1 else 0
                
                # Passo 2: Extrair os dados estritamente coordenados por célula
                for idx, row in df.iterrows():
                    val_celula = str(row[col_valor_idx]) if col_valor_idx < len(row) else ""
                    ped_celula = str(row[col_pedido_idx]) if col_pedido_idx < len(row) else ""
                    loc_celula = str(row[col_loc_idx]) if (col_loc_idx is not None and col_loc_idx < len(row)) else ""
                    
                    v_puro = limpar_valor(val_celula)
                    
                    # Limpa o número do pedido capturado na célula (deve ter de 3 a 7 dígitos e não ser o ano corrente)
                    ped_limpo = "N/A"
                    ped_match = re.search(r'\b(\d{3,7})\b', ped_celula)
                    if ped_match and ped_match.group(1) not in ["2025", "2026", "2027", "0226"]:
                        ped_limpo = ped_match.group(1)
                        
                    loc_limpo = None
                    loc_match = re.search(r'\b([A-Z0-9]{6})\b', loc_celula.upper())
                    if loc_match and not loc_match.group(1).isdigit():
                        loc_limpo = loc_match.group(1)
                    
                    if v_puro > 0:
                        banco_de_dados_viagens.append({
                            "Loc": loc_limpo,
                            "Pedido": ped_limpo,
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
                    
                    # Comparação precisa baseada em dados de célula
                    for p in banco_de_dados_viagens:
                        if loc_fatura and p['Loc'] and loc_fatura == p['Loc']:
                            pedido_encontrado = p['Pedido']
                            break
                        # Margem flexível de corte para taxas agregadas em faturas de hotéis/hospedagem (até R$ 55,00 de diferença de ISS/Taxa)
                        elif abs(valor_fatura_puro - p['ValorPuro']) < 55.00:
                            if "EXPEDIA" in descricao.upper() or "HOTEL" in descricao.upper() or "AIRBNB" in descricao.upper():
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

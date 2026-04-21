import pandas as pd
import yfinance as yf
import fundamentus
import time
from datetime import datetime
import os

print("🤖 Iniciando o Robô de Coleta de Balanços...")
print("-" * 50)

# --- 1. NOSSAS LISTAS DE ATIVOS ---
acoes_br_list = [
    "AGRO3", "AMOB3", "BBAS3", "BBDC3", "BBSE3", "BRSR6", "B3SA3", "CMIG3", 
    "CXSE3", "EGIE3", "EQTL3", "EZTC3", "FLRY3", "GMAT3", "ITSA4", "KEPL3", 
    "KLBN3", "LEVE3", "PETR3", "PRIO3", "PSSA3", "RAIZ4", "RANI3", "SAPR4", 
    "SBFG3", "SMTO3", "SOJA3", "SUZB3", "TAEE11", "TTEN3", "VAMO3", "VIVT3", "WEGE3"
]

acoes_usa_list = [
    "GOOGL", "AMZN", "NVDA", "TSM", "ASML", "AVGO", "IRS", "TSLA", "MU", "VZ", 
    "T", "HD", "SHOP", "DIS", "SPG", "ANET", "ICE", "KO", "EQNR", "EPR", "WFC", 
    "VICI", "O", "CPRT", "ASX", "CEPU", "NVO", "PLTR", "JBL", "QCOM", "AAPL", 
    "MSFT", "BAC", "ORCL", "EQT", "MNST", "CVS", "HUYA", "GPC", "PFE", "ROKU", 
    "DIBS", "LEG", "MBUU", "FVRR"
]

# DataFrame vazio para irmos guardando os dados
df_final = pd.DataFrame()

# --- 2. COLETA BRASIL (VIA FUNDAMENTUS) ---
print("🇧🇷 Etapa 1: Coletando dados da B3 (Fundamentus)...")
try:
    # O Fundamentus puxa TODAS as ações da bolsa em 2 segundos
    df_b3_completo = fundamentus.get_resultado()
    
    # Filtramos apenas as 33 que nos interessam
    df_br = df_b3_completo[df_b3_completo.index.isin(acoes_br_list)].copy()
    
    # Resetar o index para a coluna 'Papel' virar coluna normal (Ticker)
    df_br.reset_index(inplace=True)
    df_br.rename(columns={'papel': 'Ticker'}, inplace=True)
    
    # Matemática do Valuation: Descobrir LPA e VPA a partir do Preço, P/L e P/VP
    df_br['Preco'] = df_br['cotacao']
    df_br['LPA'] = df_br['Preco'] / df_br['pl']
    df_br['VPA'] = df_br['Preco'] / df_br['pvp']
    df_br['Div_Yield_%'] = df_br['dy'] * 100
    df_br['ROE_%'] = df_br['roe'] * 100
    df_br['ROIC_%'] = df_br['roic'] * 100
    df_br['EV_EBIT'] = df_br['evebit']
    
    # Selecionar e padronizar apenas as colunas que importam para o nosso painel
    df_br_limpo = df_br[['Ticker', 'Preco', 'LPA', 'VPA', 'Div_Yield_%', 'ROE_%', 'ROIC_%', 'EV_EBIT']].copy()
    df_br_limpo['Origem'] = "BRAPI/Fundamentus"
    
    df_final = pd.concat([df_final, df_br_limpo], ignore_index=True)
    print(f"✅ Sucesso! {len(df_br_limpo)} ações brasileiras processadas.")
except Exception as e:
    print(f"❌ Erro na coleta Brasil: {e}")

# --- 3. COLETA EUA (VIA YFINANCE COM "FILA INDIANA") ---
print("\n🇺🇸 Etapa 2: Coletando dados dos EUA (Yahoo Finance)...")
dados_usa = []

# Configuração da Fila Indiana
tamanho_lote = 10
pausa_segundos = 3

for i in range(0, len(acoes_usa_list), tamanho_lote):
    lote = acoes_usa_list[i:i + tamanho_lote]
    print(f"⏳ Processando lote {i//tamanho_lote + 1}... Ativos: {lote}")
    
    for ticker in lote:
        try:
            acao = yf.Ticker(ticker)
            info = acao.info
            
            # Buscando as informações (com 'fallback' de 0 caso a empresa não tenha)
            preco = info.get('currentPrice', info.get('previousClose', 0))
            lpa = info.get('trailingEps', 0)
            vpa = info.get('bookValue', 0)
            dy = info.get('dividendYield', 0)
            roe = info.get('returnOnEquity', 0)
            
            # Aproximação de EV/EBIT (A Fórmula Mágica)
            ev = info.get('enterpriseValue', 0)
            ebitda = info.get('ebitda', 0)
            ev_ebit = ev / ebitda if ebitda and ev else 0
            
            dados_usa.append({
                'Ticker': ticker,
                'Preco': preco,
                'LPA': lpa,
                'VPA': vpa,
                'Div_Yield_%': (dy * 100) if dy else 0,
                'ROE_%': (roe * 100) if roe else 0,
                'ROIC_%': 0, # YF não fornece ROIC fácil, deixamos 0 nesta versão
                'EV_EBIT': ev_ebit,
                'Origem': "Yahoo Finance"
            })
            
        except Exception as e:
            print(f"⚠️ Erro ao processar {ticker}: {e}")
            
    # Pausa intencional para evitar o Erro 429
    if i + tamanho_lote < len(acoes_usa_list):
        print(f"💤 Pausando {pausa_segundos}s para respeitar o limite do servidor...")
        time.sleep(pausa_segundos)

if dados_usa:
    df_usa_limpo = pd.DataFrame(dados_usa)
    df_final = pd.concat([df_final, df_usa_limpo], ignore_index=True)
    print(f"✅ Sucesso! {len(dados_usa)} ações americanas processadas.")

# --- 4. SALVANDO O BANCO DE DADOS (CSV) ---
print("\n💾 Etapa 3: Gerando o arquivo base_dados.csv...")

if not df_final.empty:
    # Arredondando tudo para 4 casas decimais para ficar limpo
    df_final = df_final.round(4)
    
    # Carimbando a data da extração (Governança)
    data_extracao = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    
    # Salva o arquivo CSV
    caminho_arquivo = "base_dados.csv"
    df_final.to_csv(caminho_arquivo, index=False, sep=";")
    
    print("-" * 50)
    print(f"🎉 CONCLUÍDO! Banco de dados atualizado com sucesso em {data_extracao}.")
    print(f"O arquivo '{caminho_arquivo}' já pode ser lido pelo painel Streamlit.")
else:
    print("❌ Erro fatal: Nenhum dado foi coletado.")
import pandas as pd
import yfinance as yf
import fundamentus
import requests
import time
from datetime import datetime
import os
from dotenv import load_dotenv

# --- CONFIGURAÇÃO DE SEGURANÇA (COFRE LOCAL) ---
# O comando abaixo lê o arquivo .env silenciosamente
load_dotenv() 

BRAPI_KEY = os.getenv("BRAPI_KEY")
FINNHUB_KEY = os.getenv("FINNHUB_KEY")

if not BRAPI_KEY or not FINNHUB_KEY:
    print("❌ ERRO: Chaves não encontradas! Verifique o arquivo .env")
    exit()

print("🤖 Robô V2.0: Iniciando Coleta Pro (BRAPI + FINNHUB)...")

# --- LISTAS DE ATIVOS ---
acoes_br_list = ["AGRO3", "AMOB3", "BBAS3", "BBDC3", "BBSE3", "BRSR6", "B3SA3", "CMIG3", "CXSE3", "EGIE3", "EQTL3", "EZTC3", "FLRY3", "GMAT3", "ITSA4", "KEPL3", "KLBN3", "LEVE3", "PETR3", "PRIO3", "PSSA3", "RAIZ4", "RANI3", "SAPR4", "SBFG3", "SMTO3", "SOJA3", "SUZB3", "TAEE11", "TTEN3", "VAMO3", "VIVT3", "WEGE3"]
acoes_usa_list = ["GOOGL", "AMZN", "NVDA", "TSM", "ASML", "AVGO", "IRS", "TSLA", "MU", "VZ", "T", "HD", "SHOP", "DIS", "SPG", "ANET", "ICE", "KO", "EQNR", "EPR", "WFC", "VICI", "O", "CPRT", "ASX", "CEPU", "NVO", "PLTR", "JBL", "QCOM", "AAPL", "MSFT", "BAC", "ORCL", "EQT", "MNST", "CVS", "HUYA", "GPC", "PFE", "ROKU", "DIBS", "LEG", "MBUU", "FVRR"]

df_final = pd.DataFrame()

# --- 1. BRASIL (VIA FUNDAMENTUS/BRAPI) ---
print("🇧🇷 Processando Brasil...")
try:
    df_br = fundamentus.get_resultado()
    df_br = df_br[df_br.index.isin(acoes_br_list)].copy()
    df_br.reset_index(inplace=True)
    df_br.rename(columns={'papel': 'Ticker', 'cotacao': 'Preco', 'pl': 'PL', 'pvp': 'PVP'}, inplace=True)
    
    df_br['LPA'] = df_br['Preco'] / df_br['PL']
    df_br['VPA'] = df_br['Preco'] / df_br['PVP']
    df_br['Div_Yield_%'] = df_br['dy'] * 100
    df_br['ROE_%'] = df_br['roe'] * 100
    df_br['ROIC_%'] = df_br['roic'] * 100
    df_br['EV_EBIT'] = df_br['evebit']
    df_br['Origem'] = "BRAPI/Fundamentus"
    
    df_final = pd.concat([df_final, df_br[['Ticker', 'Preco', 'LPA', 'VPA', 'Div_Yield_%', 'ROE_%', 'ROIC_%', 'EV_EBIT', 'Origem']]])
    print("✅ Brasil concluído.")
except Exception as e: print(f"❌ Erro Brasil: {e}")

# --- 2. EUA (HÍBRIDO: YAHOO FINANCE + FINNHUB) ---
print("\n🇺🇸 Processando EUA (Motor Híbrido: YF + Finnhub)...")
dados_usa = []

for ticker in acoes_usa_list:
    try:
        # 1. Puxa a contabilidade perfeita e atualizada do Yahoo Finance
        acao = yf.Ticker(ticker)
        info = acao.info
        
        # 2. Puxa APENAS a métrica faltante (ROIC) do Finnhub
        url = f"https://finnhub.io/api/v1/stock/metric?symbol={ticker}&metric=all&token={FINNHUB_KEY}"
        res = requests.get(url).json()
        metrics = res.get('metric', {})
        
        # Coleta os dados básicos do Yahoo
        preco = info.get('currentPrice', info.get('previousClose', 0))
        lpa = info.get('trailingEps', 0)
        vpa = info.get('bookValue', 0)
        
        dy = info.get('dividendYield')
        dy_val = (dy * 100) if dy is not None else 0
        
        roe = info.get('returnOnEquity')
        roe_val = (roe * 100) if roe is not None else 0
        
        # O EV/EBITDA o Yahoo tem prontinho e perfeito
        ev_ebit_val = info.get('enterpriseToEbitda', 0)
        
        # O Segredo do Finnhub: No plano gratuito eles chamam o ROIC de 'roiTTM'
        roic_val = metrics.get('roiTTM', metrics.get('roiAnnual', 0))
        
        dados_usa.append({
            'Ticker': ticker,
            'Preco': preco,
            'LPA': lpa,
            'VPA': vpa,
            'Div_Yield_%': dy_val,
            'ROE_%': roe_val,
            'ROIC_%': roic_val,
            'EV_EBIT': ev_ebit_val,
            'Origem': "YF + Finnhub"
        })
        print(f"✔️ {ticker}: Coletado (EV/EBIT e ROIC OK).")
        
        # Nossa pausa estratégica para não estourar os limites
        time.sleep(1.1)
        
    except Exception as e: 
        print(f"⚠️ Erro no ativo {ticker}: {e}")

df_final = pd.concat([df_final, pd.DataFrame(dados_usa)], ignore_index=True)
df_final.to_csv("base_dados.csv", index=False, sep=";")
print(f"\n🎉 Concluído em {datetime.now().strftime('%H:%M:%S')}. Base salva!")
import pandas as pd
import yfinance as yf
import fundamentus
import requests
import time
from datetime import datetime
import os
from dotenv import load_dotenv

# --- CONFIGURAÇÃO DE SEGURANÇA ---
load_dotenv() # Abre o cofre local (.env)

BRAPI_KEY = os.getenv("BRAPI_KEY")
FINNHUB_KEY = os.getenv("FINNHUB_KEY")

if not BRAPI_KEY or not FINNHUB_KEY:
    print("❌ ERRO: Chaves não encontradas! Verifique o arquivo .env")
    exit()

print("🤖 Robô V3.0 (Fase 2): Extraindo Fundamentos e Projeções de Crescimento...")

acoes_br_list = ["AGRO3", "AMOB3", "BBAS3", "BBDC3", "BBSE3", "BRSR6", "B3SA3", "CMIG3", "CXSE3", "EGIE3", "EQTL3", "EZTC3", "FLRY3", "GMAT3", "ITSA4", "KEPL3", "KLBN3", "LEVE3", "PETR3", "PRIO3", "PSSA3", "RAIZ4", "RANI3", "SAPR4", "SBFG3", "SMTO3", "SOJA3", "SUZB3", "TAEE11", "TTEN3", "VAMO3", "VIVT3", "WEGE3"]
acoes_usa_list = ["GOOGL", "AMZN", "NVDA", "TSM", "ASML", "AVGO", "IRS", "TSLA", "MU", "VZ", "T", "HD", "SHOP", "DIS", "SPG", "ANET", "ICE", "KO", "EQNR", "EPR", "WFC", "VICI", "O", "CPRT", "ASX", "CEPU", "NVO", "PLTR", "JBL", "QCOM", "AAPL", "MSFT", "BAC", "ORCL", "EQT", "MNST", "CVS", "HUYA", "GPC", "PFE", "ROKU", "DIBS", "LEG", "MBUU", "FVRR"]

df_final = pd.DataFrame()

# --- 1. BRASIL (VIA FUNDAMENTUS) ---
print("🇧🇷 Processando Brasil...")
try:
    df_br = fundamentus.get_resultado()
    df_br = df_br[df_br.index.isin(acoes_br_list)].copy()
    df_br.reset_index(inplace=True)
    df_br.rename(columns={'papel': 'Ticker', 'cotacao': 'Preco', 'pl': 'PL', 'pvp': 'PVP'}, inplace=True)
    
    # Métricas Base
    df_br['LPA'] = df_br['Preco'] / df_br['PL']
    df_br['VPA'] = df_br['Preco'] / df_br['PVP']
    df_br['Div_Yield_%'] = df_br.get('dy', 0) * 100
    df_br['ROE_%'] = df_br.get('roe', 0) * 100
    df_br['ROIC_%'] = df_br.get('roic', 0) * 100
    df_br['EV_EBIT'] = df_br.get('evebit', 0)
    
    # NOVAS MÉTRICAS FASE 2 (Blindadas)
    # A biblioteca Fundamentus usa a chave 'c5y' para o crescimento de 5 anos
    df_br['Crescimento_5a_%'] = df_br.get('c5y', 0) * 100
    df_br['Margem_Liquida_%'] = df_br.get('mrgliq', 0) * 100
    df_br['Liquidez_Corrente'] = df_br.get('liqc', 0)
    
    df_br['Origem'] = "BRAPI/Fundamentus"
    
    colunas_finais = ['Ticker', 'Preco', 'LPA', 'VPA', 'Div_Yield_%', 'ROE_%', 'ROIC_%', 'EV_EBIT', 'Crescimento_5a_%', 'Margem_Liquida_%', 'Liquidez_Corrente', 'Origem']
    df_final = pd.concat([df_final, df_br[colunas_finais]])
    print("✅ Brasil concluído.")
except Exception as e: 
    print(f"❌ Erro Brasil: {e}")

# --- 2. EUA (MOTOR HÍBRIDO YF + FINNHUB) ---
print("\n🇺🇸 Processando EUA (Motor Híbrido)...")
dados_usa = []
for ticker in acoes_usa_list:
    try:
        # Yahoo Finance (Contabilidade Pura)
        acao = yf.Ticker(ticker)
        info = acao.info
        
        # Finnhub (Métricas Específicas)
        url = f"https://finnhub.io/api/v1/stock/metric?symbol={ticker}&metric=all&token={FINNHUB_KEY}"
        res = requests.get(url).json()
        metrics = res.get('metric', {})
        
        preco = info.get('currentPrice', info.get('previousClose', 0))
        lpa = info.get('trailingEps', 0)
        vpa = info.get('bookValue', 0)
        dy = info.get('dividendYield')
        roe = info.get('returnOnEquity')
        
        dados_usa.append({
            'Ticker': ticker,
            'Preco': preco,
            'LPA': lpa,
            'VPA': vpa,
            'Div_Yield_%': (dy * 100) if dy is not None else 0,
            'ROE_%': (roe * 100) if roe is not None else 0,
            'ROIC_%': metrics.get('roiTTM', metrics.get('roiAnnual', 0)),
            'EV_EBIT': info.get('enterpriseToEbitda', 0),
            
            # NOVAS MÉTRICAS FASE 2 (DCF e F-Score)
            'Crescimento_5a_%': metrics.get('epsGrowth5Y', metrics.get('revenueGrowth5Y', 0)),
            'Margem_Liquida_%': metrics.get('netProfitMarginTTM', metrics.get('netProfitMarginAnnual', 0)),
            'Liquidez_Corrente': metrics.get('currentRatioQuarterly', metrics.get('currentRatioAnnual', 0)),
            
            'Origem': "YF + Finnhub"
        })
        print(f"✔️ {ticker}: Coletado.")
        time.sleep(1.1)
    except Exception as e: print(f"⚠️ Erro no ativo {ticker}: {e}")

df_final = pd.concat([df_final, pd.DataFrame(dados_usa)], ignore_index=True)

# Arredondar tudo para evitar dízimas periódicas no CSV
df_final = df_final.round(4)
df_final.to_csv("base_dados.csv", index=False, sep=";")
print(f"\n🎉 Sprint 2 - Preparação Concluída em {datetime.now().strftime('%H:%M:%S')}. Base salva!")
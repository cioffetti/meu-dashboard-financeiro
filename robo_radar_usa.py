import os
import time
import pandas as pd
import yfinance as yf
import requests
import io

# Ações que JÁ ESTÃO no seu app.py (Não gastamos tempo com elas)
ativos_ja_monitorados_usa = ["GOOGL", "AMZN", "NVDA", "TSM", "ASML", "AVGO", "IRS", "TSLA", "MU", "VZ", "T", "HD", "SHOP", "DIS", "SPG", "ANET", "ICE", "KO", "EQNR", "EPR", "WFC", "VICI", "O", "CPRT", "ASX", "CEPU", "NVO", "PLTR", "JBL", "QCOM", "AAPL", "MSFT", "BAC", "ORCL", "EQT", "MNST", "CVS", "HUYA", "GPC", "PFE", "ROKU", "DIBS", "LEG", "MBUU", "FVRR","SPCX"]

# --- 1. REGRAS DO CORTE FRIO (Mercado Americano) ---
ROE_MINIMO = 0.15        # 15% (Mais exigente para mercado americano maduro)
PL_MAXIMO = 25.0         # Aceitamos um P/L um pouco mais elástico para empresas de crescimento
PL_MINIMO = 2.0          

# --- 2. FUNÇÕES DE BUSCA ---
def obter_tickers_eua_completos():
    """Baixa S&P 500, Dow Jones e Nasdaq-100 da Wikipedia usando disfarce (User-Agent)"""
    tickers_brutos = set()
    
    # O "Disfarce": Simulando um navegador real
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        # 1. S&P 500
        res_sp = requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", headers=headers, timeout=10)
        sp500_df = pd.read_html(io.StringIO(res_sp.text), match="Symbol")[0]
        tickers_brutos.update(sp500_df['Symbol'].tolist())
        
        # 2. Dow Jones
        res_dow = requests.get("https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average", headers=headers, timeout=10)
        dow_df = pd.read_html(io.StringIO(res_dow.text), match="Symbol")[0]
        tickers_brutos.update(dow_df['Symbol'].tolist())
        
        # 3. Nasdaq-100
        res_nasdaq = requests.get("https://en.wikipedia.org/wiki/Nasdaq-100", headers=headers, timeout=10)
        nasdaq_df = pd.read_html(io.StringIO(res_nasdaq.text), match="Ticker")[0]
        tickers_brutos.update(nasdaq_df['Ticker'].tolist())
        
    except Exception as e:
        print(f"⚠️ Erro ao raspar alguma tabela da Wikipedia: {e}")

    # O Yahoo Finance usa hífen no lugar de ponto para classes (ex: BRK.B vira BRK-B)
    tickers_limpos = [str(t).replace('.', '-') for t in tickers_brutos]
    
    # Remove os que você já acompanha no painel principal
    alvos_finais = [t for t in tickers_limpos if t not in ativos_ja_monitorados_usa]
    
    return sorted(alvos_finais)

def avaliar_acao_usa_yf(ticker):
    """Bate no Yahoo Finance para pegar os fundamentos reais."""
    try:
        info = yf.Ticker(ticker).info
        
        roe = info.get('returnOnEquity', None)
        pl = info.get('trailingPE', None)
        preco = info.get('currentPrice', info.get('previousClose', 0))
        
        if roe is not None and pl is not None:
            if roe >= ROE_MINIMO and PL_MINIMO <= pl <= PL_MAXIMO:
                return {"Ticker": ticker, "Mercado": "USA", "Preço Atual": preco, "ROE_%": round(roe*100, 2), "P/L": round(pl, 2), "Aprovado": True, "Motivo": "Passou"}
            else:
                return {"Ticker": ticker, "Mercado": "USA", "Preço Atual": preco, "ROE_%": round(roe*100, 2), "P/L": round(pl, 2), "Aprovado": False, "Motivo": f"ROE={roe*100:.1f}% | P/L={pl:.1f}"}
        else:
            return {"Ticker": ticker, "Aprovado": False, "Motivo": "Sem ROE/PL no balanço (Prejuízo?)"}
    except Exception as e:
        return {"Ticker": ticker, "Aprovado": False, "Motivo": "Timeout/Erro na API YF"}

# --- 3. O MOTOR DE EXECUÇÃO ---
def rodar_radar_usa():
    os.system('cls' if os.name == 'nt' else 'clear')
    print("="*60)
    print("🦅 INICIANDO ROBÔ GARIMPEIRO WALL STREET (S&P 500 + DOW + NASDAQ)")
    print("="*60)
    
    print("Consolidando as três maiores listas do mercado americano...")
    alvos_usa = obter_tickers_eua_completos()
    
    if not alvos_usa:
        print("❌ Não foi possível carregar as listas.")
        return

    sobreviventes = []
    
    print(f"\n🇺🇸 Varrendo Mercado Americano ({len(alvos_usa)} ativos únicos na fila)...")
    for i, ticker in enumerate(alvos_usa):
        print(f"[{i+1:03d}/{len(alvos_usa):03d}] Analisando {ticker:<5}...", end=" ")
        
        resultado = avaliar_acao_usa_yf(ticker)
        
        if resultado["Aprovado"]:
            print(f"✅ PASSOU (ROE: {resultado['ROE_%']}% | P/L: {resultado['P/L']})")
            sobreviventes.append(resultado)
        else:
            print(f"❌ DESCARTADO ({resultado['Motivo']})")
            
        # O DESCANSO - 1 segundo para não estressar o Yahoo Finance
        time.sleep(1) 

    print("\n" + "="*60)
    print(f"🏆 FIM DA VARREDURA EUA. Sobreviventes: {len(sobreviventes)}")
    print("="*60)
    
    if sobreviventes:
        df_salvar = pd.DataFrame(sobreviventes)
        df_salvar = df_salvar[['Ticker', 'Mercado', 'Preço Atual', 'ROE_%', 'P/L']]
        
        # Modo 'a' (Append) adiciona no final do base_radar.csv sem apagar o Brasil
        df_salvar.to_csv("base_radar.csv", mode='a', header=False, sep=";", index=False)
        print("💾 Ações americanas injetadas no 'base_radar.csv' com sucesso!")
    else:
        print("Nenhuma ação sobreviveu aos seus filtros hoje.")

if __name__ == "__main__":
    rodar_radar_usa()
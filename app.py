import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import requests
from datetime import datetime
import os
from dotenv import load_dotenv

# --- CONFIGURAÇÃO DE SEGURANÇA HÍBRIDA ---
load_dotenv()
BRAPI_KEY = st.secrets.get("BRAPI_KEY", os.getenv("BRAPI_KEY", ""))
FINNHUB_KEY = st.secrets.get("FINNHUB_KEY", os.getenv("FINNHUB_KEY", ""))

# 1. CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="Dashboard Macro Pro", layout="wide")
st.title("🏛️ Monitor Financeiro - Pro")

def formatar_br(valor, casas):
    if pd.isna(valor) or valor is None: return "N/A"
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")

# --- MOTOR DE COTAÇÕES ---
@st.cache_data(ttl=300)
def buscar_dados_em_lote(lista_tickers, mercado="Macro"):
    if mercado == "BR" and BRAPI_KEY:
        try:
            tickers_limpos = [t.replace(".SA", "") for t in lista_tickers]
            url = f"https://brapi.dev/api/quote/{','.join(tickers_limpos)}?token={BRAPI_KEY}"
            res = requests.get(url, timeout=5).json()
            if 'results' in res:
                precos = {item['symbol'] + ".SA": item.get('regularMarketPrice') for item in res['results']}
                df = pd.DataFrame(list(precos.values()), index=list(precos.keys()), columns=['Close'])
                return df.T, "BRAPI"
        except Exception: pass
            
    try:
        tickers_str = " ".join(lista_tickers)
        dados = yf.download(tickers_str, period="7d", interval="1d", progress=False)
        fechamentos = pd.DataFrame(dados['Close']) if len(lista_tickers) == 1 else dados['Close']
        if len(lista_tickers) == 1: fechamentos.columns = lista_tickers
        return fechamentos, "Yahoo Finance"
    except Exception as e: return None, "ERRO"

@st.cache_data(ttl=3600)
def buscar_taxas_macro():
    selic, us10y = 10.50, 4.25
    try:
        url_bcb = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/1?formato=json"
        selic = float(requests.get(url_bcb, timeout=3).json()[0]['valor'])
    except Exception: pass
    try:
        dados_tnx = yf.download("^TNX", period="5d", progress=False)
        if not dados_tnx.empty: us10y = float(dados_tnx['Close'].iloc[-1])
    except Exception: pass
    return selic, us10y

taxa_selic_live, taxa_us10y_live = buscar_taxas_macro()

# --- 2. LISTAS DE ATIVOS ---
macro_dict = {"Dólar": ("USDBRL=X", 3), "Euro": ("EURBRL=X", 3), "Ouro": ("GC=F", 2), "Petróleo": ("BZ=F", 2), "Bitcoin": ("BTC-USD", 2), "S&P 500": ("^GSPC", 2), "Ibovespa": ("^BVSP", 2), "Nasdaq": ("^IXIC", 2)}
acoes_br_list = ["AGRO3.SA", "AMOB3.SA", "BBAS3.SA", "BBDC3.SA", "BBSE3.SA", "BRSR6.SA", "B3SA3.SA", "CMIG3.SA", "CXSE3.SA", "EGIE3.SA", "EQTL3.SA", "EZTC3.SA", "FLRY3.SA", "GMAT3.SA", "ITSA4.SA", "KEPL3.SA", "KLBN3.SA", "LEVE3.SA", "PETR3.SA", "PRIO3.SA", "PSSA3.SA", "RAIZ4.SA", "RANI3.SA", "SAPR4.SA", "SBFG3.SA", "SMTO3.SA", "SOJA3.SA", "SUZB3.SA", "TAEE11.SA", "TTEN3.SA", "VAMO3.SA", "VIVT3.SA", "WEGE3.SA"]
acoes_usa_list = ["GOOGL", "AMZN", "NVDA", "TSM", "ASML", "AVGO", "IRS", "TSLA", "MU", "VZ", "T", "HD", "SHOP", "DIS", "SPG", "ANET", "ICE", "KO", "EQNR", "EPR", "WFC", "VICI", "O", "CPRT", "ASX", "CEPU", "NVO", "PLTR", "JBL", "QCOM", "AAPL", "MSFT", "BAC", "ORCL", "EQT", "MNST", "CVS", "HUYA", "GPC", "PFE", "ROKU", "DIBS", "LEG", "MBUU", "FVRR"]

# --- 3. ABAS ---
aba_macro, aba_br, aba_usa, aba_fundamentos, aba_simulador = st.tabs([
    "🌍 Visão Macro", "🇧🇷 Ações Brasil", "🇺🇸 Ações EUA", "📊 Fundamentos", "🎛️ Simulador"
])

def renderizar_grid(dicionario, mercado):
    lista_tickers = [info[0] for info in dicionario.values()]
    dados, fonte = buscar_dados_em_lote(lista_tickers, mercado)
    if dados is not None:
        for i in range(0, len(dicionario), 4):
            cols = st.columns(4)
            for j, (nome, (ticker, casas)) in enumerate(list(dicionario.items())[i:i+4]):
                if ticker in dados.columns:
                    precos = dados[ticker].dropna()
                    if len(precos) >= 2:
                        atual = float(precos.iloc[-1])
                        var = ((atual - float(precos.iloc[-2])) / float(precos.iloc[-2])) * 100
                        with cols[j]:
                            with st.container(border=True):
                                st.metric(label=nome, value=formatar_br(atual, casas), delta=f"{var:.2f}%")
                                fig = go.Figure(go.Scatter(y=precos, line=dict(color='#00FFCC' if var >= 0 else '#FF4B4B', width=2)))
                                fig.update_layout(height=60, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

with aba_macro: renderizar_grid(macro_dict, "Macro")
with aba_br: renderizar_grid({t.replace(".SA", ""): (t, 2) for t in acoes_br_list}, "BR")
with aba_usa: renderizar_grid({t: (t, 2) for t in acoes_usa_list}, "USA")

# --- 4. CÁLCULOS TÉCNICOS ---
arquivo_csv = "base_dados.csv"
if os.path.exists(arquivo_csv):
    df = pd.read_csv(arquivo_csv, sep=";")
    
    # Valuations e Ranks
    df['Dividendo_Pago'] = df['Preco'] * (df['Div_Yield_%'] / 100)
    df['Teto_Bazin'] = df['Dividendo_Pago'] / 0.06
    df['Margem_Bazin_%'] = np.where(df['Teto_Bazin'] > 0, ((df['Teto_Bazin'] - df['Preco']) / df['Preco']) * 100, 0)
    df['Justo_Graham'] = np.where((df['LPA'] > 0) & (df['VPA'] > 0), np.sqrt(22.5 * df['LPA'] * df['VPA']), 0)
    df['Margem_Graham_%'] = np.where(df['Justo_Graham'] > 0, ((df['Justo_Graham'] - df['Preco']) / df['Preco']) * 100, 0)
    
    # F-Score (0-100)
    df['F_Score_Num'] = 0
    df.loc[df['ROE_%'] > 0, 'F_Score_Num'] += 20
    df.loc[df['Margem_Liquida_%'] > 5, 'F_Score_Num'] += 20
    df.loc[df['Liquidez_Corrente'] > 1.2, 'F_Score_Num'] += 20
    df.loc[df['Crescimento_5a_%'] > 0, 'F_Score_Num'] += 20
    df.loc[df['LPA'] > 0, 'F_Score_Num'] += 20
    df['Saude_Visual'] = (df['F_Score_Num'] / 20).apply(lambda x: "⭐" * int(x))

    # Magic Formula Rank (0-100)
    mask_m = (df['EV_EBIT'] > 0) & (df['ROIC_%'] > 0)
    df.loc[mask_m, 'Rank_Magic'] = (df.loc[mask_m, 'ROIC_%'].rank() + df.loc[mask_m, 'EV_EBIT'].rank(ascending=False)).rank(pct=True) * 100

    # Aba Fundamentos (Estática)
    with aba_fundamentos:
        st.header("Radar de Fundamentos")
        mercado_f = st.radio("Filtro:", ["Todos", "Brasil", "EUA"], horizontal=True, key="f_m")
        df_f = df.copy()
        if mercado_f == "Brasil": df_f = df_f[df_f['Origem'].str.contains("BRAPI", na=False)]
        elif mercado_f == "EUA": df_f = df_f[df_f['Origem'].str.contains("Finnhub", na=False)]
        st.dataframe(df_f[['Ticker', 'Preco', 'Saude_Visual', 'ROIC_%', 'EV_EBIT', 'Teto_Bazin', 'Justo_Graham']], use_container_width=True, hide_index=True)

    # Aba Simulador (DINÂMICA)
    with aba_simulador:
        st.header("🎛️ Simulador de Estratégia")
        with st.expander("Defina seus Pesos de Decisão", expanded=True):
            c1, c2, c3, c4, c5 = st.columns(5)
            w_graham = c1.slider("Valor (Graham)", 0, 100, 20)
            w_bazin = c2.slider("Renda (Bazin)", 0, 100, 20)
            w_magic = c3.slider("Qualidade (Magic)", 0, 100, 20)
            w_fscore = c4.slider("Saúde (F-Score)", 0, 100, 20)
            w_dcf = c5.slider("Futuro (DCF)", 0, 100, 20)
            
            taxa_br = st.sidebar.number_input("Selic Meta %", 4.0, 18.0, taxa_selic_live)
            taxa_us = st.sidebar.number_input("US 10Y %", 1.0, 10.0, taxa_us10y_live)

        # Cálculo do DCF Dinâmico para o Simulador
        df['Taxa'] = np.where(df['Origem'].str.contains("BRAPI"), taxa_br, taxa_us)
        df['Justo_DCF'] = np.where(df['LPA'] > 0, df['LPA'] * (8.5 + 2 * df['Crescimento_5a_%'].clip(0,15)) * (4.4 / df['Taxa']), 0)
        df['Margem_DCF_%'] = np.where(df['Justo_DCF'] > 0, ((df['Justo_DCF'] - df['Preco']) / df['Preco']) * 100, 0)

        # Normalização de Ranks (0 a 100)
        df['N_Graham'] = df['Margem_Graham_%'].rank(pct=True) * 100
        df['N_Bazin'] = df['Margem_Bazin_%'].rank(pct=True) * 100
        df['N_DCF'] = df['Margem_DCF_%'].rank(pct=True) * 100
        
        total_w = w_graham + w_bazin + w_magic + w_fscore + w_dcf
        if total_w > 0:
            df['Nota_Final'] = (
                (df['N_Graham'] * w_graham) + (df['N_Bazin'] * w_bazin) + 
                (df['Rank_Magic'].fillna(0) * w_magic) + (df['F_Score_Num'] * w_fscore) + 
                (df['N_DCF'] * w_dcf)
            ) / total_w
        else: df['Nota_Final'] = 0

        df_s = df.sort_values(by='Nota_Final', ascending=False).copy()
        df_s['Veredito'] = pd.cut(df_s['Nota_Final'], bins=[0, 40, 70, 100], labels=["Neutro", "Estudo", "Compra Forte"])
        
        st.subheader("🏆 Ranking de Convergência Customizado")
        st.dataframe(df_s[['Ticker', 'Preco', 'Nota_Final', 'Veredito', 'Saude_Visual']], use_container_width=True)

else: st.warning("Execute o robô primeiro.")
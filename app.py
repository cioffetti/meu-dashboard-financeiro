import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
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

# --- MOTOR DE COTAÇÕES EM LOTE ---
@st.cache_data(ttl=300)
def buscar_dados_em_lote(lista_tickers, mercado="Macro"):
    hora_consulta = datetime.now().strftime("%H:%M")
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
    selic_atual, us10y_atual = 10.50, 4.25
    try:
        url_bcb = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/1?formato=json"
        selic_atual = float(requests.get(url_bcb, timeout=3).json()[0]['valor'])
    except Exception: pass
    try:
        dados_tnx = yf.download("^TNX", period="5d", progress=False)
        if not dados_tnx.empty: us10y_atual = float(dados_tnx['Close'].iloc[-1])
    except Exception: pass
    return selic_atual, us10y_atual

taxa_selic_live, taxa_us10y_live = buscar_taxas_macro()

# --- MOTOR DE ANÁLISE TÉCNICA (NOVO - FASE 3) ---
def calcular_indicadores_tecnicos(df):
    # Bandas de Bollinger (Volatilidade)
    df['SMA_20'] = df['Close'].rolling(window=20).mean()
    df['STD_20'] = df['Close'].rolling(window=20).std()
    df['Bollinger_Upper'] = df['SMA_20'] + (df['STD_20'] * 2)
    df['Bollinger_Lower'] = df['SMA_20'] - (df['STD_20'] * 2)
    
    # MACD (Tendência)
    df['EMA_12'] = df['Close'].ewm(span=12, adjust=False).mean()
    df['EMA_26'] = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = df['EMA_12'] - df['EMA_26']
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']
    
    # RSI (Força Relativa - Exaustão)
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    return df

def encontrar_suportes_resistencias(df):
    suportes, resistencias = [], []
    # Janela de rolagem para encontrar picos e vales
    for i in range(20, len(df)-20):
        if df['Low'].iloc[i] == min(df['Low'].iloc[i-20:i+20]): suportes.append(df['Low'].iloc[i])
        if df['High'].iloc[i] == max(df['High'].iloc[i-20:i+20]): resistencias.append(df['High'].iloc[i])
    
    preco_atual = df['Close'].iloc[-1]
    # Filtra os 3 suportes mais próximos abaixo do preço e 3 resistências acima
    suportes_filtrados = sorted([s for s in suportes if s < preco_atual], reverse=True)[:3]
    resistencias_filtradas = sorted([r for r in resistencias if r > preco_atual])[:3]
    return suportes_filtrados, resistencias_filtradas

@st.dialog("🔬 Raio-X Técnico Profissional")
def abrir_raio_x(ticker):
    st.write(f"Buscando histórico de 5 anos para **{ticker}** e calculando algoritmos...")
    # Busca sob demanda
    try:
        dados = yf.download(ticker, period="5y", progress=False)
        if dados.empty:
            st.error("Dados não encontrados para este ativo.")
            return
            
        df_tec = calcular_indicadores_tecnicos(dados)
        suportes, resistencias = encontrar_suportes_resistencias(df_tec)
        df_tec = df_tec.tail(250) # Mostra no gráfico apenas o último 1 ano útil para clareza
        
        # Criação do Painel Triplo Sincronizado
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, row_heights=[0.6, 0.2, 0.2], vertical_spacing=0.05)
        
        # 1. Gráfico Principal (Candle + Bollinger + S/R)
        fig.add_trace(go.Candlestick(x=df_tec.index, open=df_tec['Open'], high=df_tec['High'], low=df_tec['Low'], close=df_tec['Close'], name='Preço'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_tec.index, y=df_tec['Bollinger_Upper'], line=dict(color='rgba(255,255,255,0.2)', width=1), name='Banda Sup'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_tec.index, y=df_tec['Bollinger_Lower'], line=dict(color='rgba(255,255,255,0.2)', width=1), fill='tonexty', fillcolor='rgba(255,255,255,0.05)', name='Banda Inf'), row=1, col=1)
        
        for s in suportes:
            fig.add_hline(y=s, line_dash="dash", line_color="green", annotation_text=f"Suporte: {s:.2f}", row=1, col=1)
        for r in resistencias:
            fig.add_hline(y=r, line_dash="dash", line_color="red", annotation_text=f"Resist: {r:.2f}", row=1, col=1)

        # 2. MACD + Volume
        cores_macd = ['#00FFCC' if val >= 0 else '#FF4B4B' for val in df_tec['MACD_Hist']]
        fig.add_trace(go.Bar(x=df_tec.index, y=df_tec['Volume'], marker_color='rgba(255,255,255,0.1)', name='Volume'), row=2, col=1)
        fig.add_trace(go.Scatter(x=df_tec.index, y=df_tec['MACD'], line=dict(color='blue', width=1.5), name='MACD'), row=2, col=1)
        fig.add_trace(go.Scatter(x=df_tec.index, y=df_tec['MACD_Signal'], line=dict(color='orange', width=1.5), name='Sinal'), row=2, col=1)
        fig.add_trace(go.Bar(x=df_tec.index, y=df_tec['MACD_Hist'], marker_color=cores_macd, name='Histograma'), row=2, col=1)

        # 3. RSI
        fig.add_trace(go.Scatter(x=df_tec.index, y=df_tec['RSI'], line=dict(color='purple', width=2), name='RSI'), row=3, col=1)
        fig.add_hline(y=70, line_dash="dot", line_color="red", row=3, col=1)
        fig.add_hline(y=30, line_dash="dot", line_color="green", row=3, col=1)

        fig.update_layout(height=700, template="plotly_dark", showlegend=False, margin=dict(l=0, r=0, t=10, b=0), xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)
        
        # Veredito Técnico Matemático
        rsi_atual = df_tec['RSI'].iloc[-1]
        preco_atual = df_tec['Close'].iloc[-1]
        st.markdown(f"**RSI Atual:** {rsi_atual:.1f} (Abaixo de 30 = Sobrevendido / Acima de 70 = Sobrecomprado)")
        if suportes:
            st.markdown(f"**Distância para o Piso Seguro:** Faltam {(preco_atual - suportes[0]) / preco_atual * 100:.2f}% de queda para atingir o suporte mais forte.")

    except Exception as e:
        st.error(f"Erro ao processar Raio-X: {e}")

# --- 2. LISTAS DE ATIVOS ---
macro_dict = {"Dólar": ("USDBRL=X", 3), "Euro": ("EURBRL=X", 3), "Ouro": ("GC=F", 2), "Petróleo": ("BZ=F", 2), "Bitcoin": ("BTC-USD", 2), "S&P 500": ("^GSPC", 2), "Ibovespa": ("^BVSP", 2), "Nasdaq": ("^IXIC", 2)}
acoes_br_list = ["AGRO3.SA", "AMOB3.SA", "BBAS3.SA", "BBDC3.SA", "BBSE3.SA", "BRSR6.SA", "B3SA3.SA", "CMIG3.SA", "CXSE3.SA", "EGIE3.SA", "EQTL3.SA", "EZTC3.SA", "FLRY3.SA", "GMAT3.SA", "ITSA4.SA", "KEPL3.SA", "KLBN3.SA", "LEVE3.SA", "PETR3.SA", "PRIO3.SA", "PSSA3.SA", "RAIZ4.SA", "RANI3.SA", "SAPR4.SA", "SBFG3.SA", "SMTO3.SA", "SOJA3.SA", "SUZB3.SA", "TAEE11.SA", "TTEN3.SA", "VAMO3.SA", "VIVT3.SA", "WEGE3.SA", "ETHE11.SA", "GOLD11.SA", "QSOL11.SA", "QBTC11.SA"]
acoes_usa_list = ["GOOGL", "AMZN", "NVDA", "TSM", "ASML", "AVGO", "IRS", "TSLA", "MU", "VZ", "T", "HD", "SHOP", "DIS", "SPG", "ANET", "ICE", "KO", "EQNR", "EPR", "WFC", "VICI", "O", "CPRT", "ASX", "CEPU", "NVO", "PLTR", "JBL", "QCOM", "AAPL", "MSFT", "BAC", "ORCL", "EQT", "MNST", "CVS", "HUYA", "GPC", "PFE", "ROKU", "DIBS", "LEG", "MBUU", "FVRR"]

# --- 3. ABAS ---
aba_macro, aba_br, aba_usa, aba_fundamentos, aba_tecnica, aba_simulador = st.tabs([
    "🌍 Visão Macro", "🇧🇷 Ações Brasil", "🇺🇸 Ações EUA", "📊 Fundamentos", "🔬 Raio-X Técnico", "🎛️ Simulador"
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

# --- 4. ABA DE RAIO-X TÉCNICO (NOVA) ---
with aba_tecnica:
    st.header("🔬 Análise Técnica e Algoritmo de Suportes")
    st.write("Selecione um ativo para abrir o detalhamento profundo de timing.")
    
    col1, col2 = st.columns([1, 2])
    todos_ativos = [t for t in acoes_br_list + acoes_usa_list if "11.SA" not in t] # Exclui ETFs do motor técnico
    ativo_selecionado = col1.selectbox("Escolha a Ação:", sorted(todos_ativos))
    
    if col1.button("🔍 Abrir Raio-X Técnico", use_container_width=True):
        abrir_raio_x(ativo_selecionado)

# --- 5. CÁLCULOS DE VALUATION E SIMULADOR ---
arquivo_csv = "base_dados.csv"
if os.path.exists(arquivo_csv):
    df = pd.read_csv(arquivo_csv, sep=";")
    df['Dividendo_Pago'] = df['Preco'] * (df['Div_Yield_%'] / 100)
    df['Teto_Bazin'] = df['Dividendo_Pago'] / 0.06
    df['Margem_Bazin_%'] = np.where(df['Teto_Bazin'] > 0, ((df['Teto_Bazin'] - df['Preco']) / df['Preco']) * 100, 0)
    df['Justo_Graham'] = np.where((df['LPA'] > 0) & (df['VPA'] > 0), np.sqrt(22.5 * df['LPA'] * df['VPA']), 0)
    df['Margem_Graham_%'] = np.where(df['Justo_Graham'] > 0, ((df['Justo_Graham'] - df['Preco']) / df['Preco']) * 100, 0)
    
    df['F_Score_Num'] = 0
    df.loc[df['ROE_%'] > 0, 'F_Score_Num'] += 20
    df.loc[df['Margem_Liquida_%'] > 5, 'F_Score_Num'] += 20
    df.loc[df['Liquidez_Corrente'] > 1.2, 'F_Score_Num'] += 20
    df.loc[df['Crescimento_5a_%'] > 0, 'F_Score_Num'] += 20
    df.loc[df['LPA'] > 0, 'F_Score_Num'] += 20
    df['Saude_Visual'] = (df['F_Score_Num'] / 20).apply(lambda x: "⭐" * int(x))

    mask_m = (df['EV_EBIT'] > 0) & (df['ROIC_%'] > 0)
    df.loc[mask_m, 'Rank_Magic'] = (df.loc[mask_m, 'ROIC_%'].rank() + df.loc[mask_m, 'EV_EBIT'].rank(ascending=False)).rank(pct=True) * 100

    # Fundamentos (Restaurado e Estático)
    with aba_fundamentos:
        st.header("Radar de Fundamentos e Qualidade")
        mercado_f = st.radio("Filtro:", ["Todos", "Ações Brasil", "Ações EUA"], horizontal=True, key="f_m")
        df_f = df.copy()
        if mercado_f == "Ações Brasil": df_f = df_f[df_f['Origem'].str.contains("BRAPI", na=False)]
        elif mercado_f == "Ações EUA": df_f = df_f[df_f['Origem'].str.contains("Finnhub", na=False)]
        st.dataframe(df_f[['Ticker', 'Preco', 'Saude_Visual', 'ROIC_%', 'EV_EBIT', 'Teto_Bazin', 'Justo_Graham', 'Margem_Bazin_%', 'Margem_Graham_%']], use_container_width=True, hide_index=True)

    # Simulador (Intacto)
    with aba_simulador:
        st.header("🎛️ Laboratório de Estratégia Ponderada")
        with st.expander("Defina seus Pesos de Decisão (0 a 100%)", expanded=True):
            c1, c2, c3, c4, c5 = st.columns(5)
            w_graham = c1.slider("Valor (Graham)", 0, 100, 20)
            w_bazin = c2.slider("Renda (Bazin)", 0, 100, 20)
            w_magic = c3.slider("Qualidade (Magic)", 0, 100, 20)
            w_fscore = c4.slider("Saúde (F-Score)", 0, 100, 20)
            w_dcf = c5.slider("Futuro (DCF)", 0, 100, 20)

        df_sim = df.copy()
        df_sim['Taxa_Aplicada'] = np.where(df_sim['Origem'].str.contains("BRAPI"), taxa_selic_live, taxa_us10y_live)
        df_sim['Justo_DCF'] = np.where(df_sim['LPA'] > 0, df_sim['LPA'] * (8.5 + 2 * df_sim['Crescimento_5a_%'].clip(0,15)) * (4.4 / df_sim['Taxa_Aplicada']), 0)
        df_sim['Margem_DCF_%'] = np.where(df_sim['Justo_DCF'] > 0, ((df_sim['Justo_DCF'] - df_sim['Preco']) / df_sim['Preco']) * 100, 0)

        df_sim['N_Graham'] = df_sim['Margem_Graham_%'].rank(pct=True) * 100
        df_sim['N_Bazin'] = df_sim['Margem_Bazin_%'].rank(pct=True) * 100
        df_sim['N_DCF'] = df_sim['Margem_DCF_%'].rank(pct=True) * 100
        df_sim['N_Magic'] = df_sim.get('Rank_Magic', pd.Series([0]*len(df_sim))).fillna(0)
        df_sim['N_FScore'] = df_sim['F_Score_Num']

        total_w = w_graham + w_bazin + w_magic + w_fscore + w_dcf
        if total_w > 0:
            df_sim['Nota_Final'] = ((df_sim['N_Graham'] * w_graham) + (df_sim['N_Bazin'] * w_bazin) + (df_sim['N_Magic'] * w_magic) + (df_sim['N_FScore'] * w_fscore) + (df_sim['N_DCF'] * w_dcf)) / total_w
        else: df_sim['Nota_Final'] = 0

        df_s = df_sim.sort_values(by='Nota_Final', ascending=False).copy()
        df_s.reset_index(drop=True, inplace=True)
        df_s.index = df_s.index + 1
        df_s['Rank'] = df_s.index.astype(str) + "º"
        
        df_s['Veredito'] = pd.cut(df_s['Nota_Final'], bins=[-1, 40, 75, 100], labels=["Neutro", "Estudo", "Compra Forte"])
        df_s['Nota_Final'] = df_s['Nota_Final'].apply(lambda x: f"{x:.1f}/100")
        
        st.dataframe(df_s[['Rank', 'Ticker', 'Preco', 'Nota_Final', 'Veredito', 'Saude_Visual']], use_container_width=True, hide_index=True)

else: st.warning("⚠️ Execute o robô primeiro.")
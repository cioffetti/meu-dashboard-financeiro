import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime

# 1. CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="Dashboard Macro Pro", layout="wide")
st.title("🏛️ Monitor Financeiro - Visão em Cartões")

# --- FUNÇÃO DE FORMATAÇÃO BRASILEIRA ---
def formatar_br(valor, casas):
    if pd.isna(valor) or valor is None: return "N/A"
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")

# --- MOTOR DE LOTE OTIMIZADO (AGORA COM CARIMBO DE TEMPO) ---
@st.cache_data(ttl=900)
def buscar_dados_em_lote(lista_tickers):
    tickers_str = " ".join(lista_tickers)
    try:
        dados = yf.download(tickers_str, period="7d", interval="1d", progress=False)
        
        # Carimba a hora exata em que fomos na internet buscar
        hora_consulta = datetime.now().strftime("%d/%m %H:%M")
        
        if len(lista_tickers) == 1:
            fechamentos = pd.DataFrame(dados['Close'])
            fechamentos.columns = lista_tickers
        else:
            fechamentos = dados['Close']
            
        return fechamentos, hora_consulta
    except Exception as e:
        st.error(f"Erro na conexão: {e}")
        return None, None

# --- 2. LISTAS DE ATIVOS (ATUALIZADAS) ---
# Formato: "Nome de Exibição": ("Ticker", Número_de_Casas)
macro_dict = {
    "Dólar": ("USDBRL=X", 3), "Euro": ("EURBRL=X", 3),
    "Ouro": ("GC=F", 2), "Petróleo (Brent)": ("BZ=F", 2),
    "Bitcoin": ("BTC-USD", 2), "Ethereum": ("ETH-USD", 2), "Solana": ("SOL-USD", 2),
    "Ibovespa": ("^BVSP", 2), "S&P 500": ("^GSPC", 2), "Dow Jones": ("^DJI", 2),
    "Nasdaq": ("^IXIC", 2), "DAX (Alem)": ("^GDAXI", 2), "Nikkei (Jap)": ("^N225", 2),
    "Shanghai (Chi)": ("000001.SS", 2), "Pequim (Chi)": ("899050.BJ", 2), "Merval (Arg)": ("^MERV", 2)
}

acoes_br_list = [
    "AGRO3.SA", "AMOB3.SA", "BBAS3.SA", "BBDC3.SA", "BBSE3.SA", 
    "BRSR6.SA", "B3SA3.SA", "CMIG3.SA", "CXSE3.SA", "EGIE3.SA", 
    "EQTL3.SA", "EZTC3.SA", "FLRY3.SA", "GMAT3.SA", "ITSA4.SA", 
    "KEPL3.SA", "KLBN3.SA", "LEVE3.SA", "PETR3.SA", "PRIO3.SA", 
    "PSSA3.SA", "RAIZ4.SA", "RANI3.SA", "SAPR4.SA", "SBFG3.SA", 
    "SMTO3.SA", "SOJA3.SA", "SUZB3.SA", "TAEE11.SA", "TTEN3.SA", 
    "VAMO3.SA", "VIVT3.SA", "WEGE3.SA"
]
acoes_br_dict = {ticker.replace(".SA", ""): (ticker, 2) for ticker in acoes_br_list}

acoes_usa_list = [
    "GOOGL", "AMZN", "NVDA", "TSM", "ASML", "AVGO", "IRS", "TSLA",
    "MU", "VZ", "T", "HD", "SHOP", "DIS", "SPG", "ANET",
    "ICE", "KO", "EQNR", "EPR", "WFC", "VICI", "O", "CPRT",
    "ASX", "CEPU", "NVO", "PLTR", "JBL", "QCOM", "AAPL", "MSFT",
    "BAC", "ORCL", "EQT", "MNST", "CVS", "HUYA", "GPC", "PFE",
    "ROKU", "DIBS", "LEG", "MBUU", "FVRR"
]
acoes_usa_dict = {ticker: (ticker, 2) for ticker in acoes_usa_list}

# --- 3. CRIAÇÃO DAS ABAS ---
aba_macro, aba_br, aba_usa = st.tabs(["🌍 Visão Macro", "🇧🇷 Ações Brasil", "🇺🇸 Ações EUA"])

def renderizar_grid_cards(dicionario_ativos):
    lista_tickers = [info[0] for info in dicionario_ativos.values()]
    
    # Agora recebemos os dados E o horário da consulta
    dados_lote, hora_consulta = buscar_dados_em_lote(lista_tickers)
    
    if dados_lote is not None:
        lista_items = list(dicionario_ativos.items())
        
        for i in range(0, len(lista_items), 4):
            cols = st.columns(4)
            for j, (nome_exibicao, (ticker, casas)) in enumerate(lista_items[i:i+4]):
                
                if ticker in dados_lote.columns:
                    precos = dados_lote[ticker].dropna()
                    
                    if len(precos) >= 2:
                        atual = float(precos.iloc[-1])
                        ontem = float(precos.iloc[-2])
                        var = ((atual - ontem) / ontem) * 100
                        
                        cor_linha = '#00FFCC' if var >= 0 else '#FF4B4B'
                        cor_preenchimento = 'rgba(0, 255, 204, 0.1)' if var >= 0 else 'rgba(255, 75, 75, 0.1)'
                        
                        with cols[j]:
                            with st.container(border=True):
                                st.metric(label=nome_exibicao, value=formatar_br(atual, casas), delta=f"{var:.2f}%".replace(".", ","))
                                
                                fig = go.Figure(go.Scatter(
                                    x=precos.index, y=precos, mode='lines', 
                                    line=dict(color=cor_linha, width=2),
                                    fill='tozeroy', fillcolor=cor_preenchimento
                                ))
                                fig.update_layout(
                                    template="plotly_dark", height=80, margin=dict(l=0,r=0,t=0,b=0),
                                    xaxis_visible=False, yaxis_visible=False, showlegend=False,
                                    plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)'
                                )
                                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
                                
                                # AQUI ENTRA A GOVERNANÇA: Mostra a hora da atualização e a fonte
                                st.caption(f"⚡ Atualizado: {hora_consulta} | Fonte: YF")

# CONTEÚDO DAS ABAS
with aba_macro:
    renderizar_grid_cards(macro_dict)

with aba_br:
    renderizar_grid_cards(acoes_br_dict)

with aba_usa:
    renderizar_grid_cards(acoes_usa_dict)
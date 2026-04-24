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
    except Exception as e:
        st.error(f"Erro no backup: {e}")
        return None, "ERRO"

# --- MOTOR AUTÔNOMO DE TAXAS MACRO (NOVO) ---
@st.cache_data(ttl=3600) # Atualiza a cada 1 hora
def buscar_taxas_macro():
    selic_atual = 10.50 # Valor de segurança (fallback)
    us10y_atual = 4.25  # Valor de segurança (fallback)
    
    # Busca a Selic Oficial (Banco Central do Brasil)
    try:
        url_bcb = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/1?formato=json"
        selic_atual = float(requests.get(url_bcb, timeout=3).json()[0]['valor'])
    except Exception: pass

    # Busca o Treasury 10Y (Yahoo Finance)
    try:
        dados_tnx = yf.download("^TNX", period="5d", progress=False)
        if not dados_tnx.empty:
            us10y_atual = float(dados_tnx['Close'].iloc[-1])
    except Exception: pass

    return selic_atual, us10y_atual

# Inicia as taxas autônomas
taxa_selic_live, taxa_us10y_live = buscar_taxas_macro()

# --- 2. LISTAS DE ATIVOS ---
macro_dict = {"Dólar": ("USDBRL=X", 3), "Euro": ("EURBRL=X", 3), "Ouro": ("GC=F", 2), "Petróleo (Brent)": ("BZ=F", 2), "Bitcoin": ("BTC-USD", 2), "Ethereum": ("ETH-USD", 2), "Solana": ("SOL-USD", 2), "Ibovespa": ("^BVSP", 2), "S&P 500": ("^GSPC", 2), "Dow Jones": ("^DJI", 2), "Nasdaq": ("^IXIC", 2), "DAX (Alem)": ("^GDAXI", 2), "Nikkei (Jap)": ("^N225", 2), "Shanghai (Chi)": ("000001.SS", 2), "Shenzhen (Chi)": ("399001.SZ", 2), "Merval (Arg)": ("^MERV", 2)}
acoes_br_list = ["AGRO3.SA", "AMOB3.SA", "BBAS3.SA", "BBDC3.SA", "BBSE3.SA", "BRSR6.SA", "B3SA3.SA", "CMIG3.SA", "CXSE3.SA", "EGIE3.SA", "EQTL3.SA", "EZTC3.SA", "FLRY3.SA", "GMAT3.SA", "ITSA4.SA", "KEPL3.SA", "KLBN3.SA", "LEVE3.SA", "PETR3.SA", "PRIO3.SA", "PSSA3.SA", "RAIZ4.SA", "RANI3.SA", "SAPR4.SA", "SBFG3.SA", "SMTO3.SA", "SOJA3.SA", "SUZB3.SA", "TAEE11.SA", "TTEN3.SA", "VAMO3.SA", "VIVT3.SA", "WEGE3.SA"]
acoes_br_dict = {ticker.replace(".SA", ""): (ticker, 2) for ticker in acoes_br_list}
acoes_usa_list = ["GOOGL", "AMZN", "NVDA", "TSM", "ASML", "AVGO", "IRS", "TSLA", "MU", "VZ", "T", "HD", "SHOP", "DIS", "SPG", "ANET", "ICE", "KO", "EQNR", "EPR", "WFC", "VICI", "O", "CPRT", "ASX", "CEPU", "NVO", "PLTR", "JBL", "QCOM", "AAPL", "MSFT", "BAC", "ORCL", "EQT", "MNST", "CVS", "HUYA", "GPC", "PFE", "ROKU", "DIBS", "LEG", "MBUU", "FVRR"]
acoes_usa_dict = {ticker: (ticker, 2) for ticker in acoes_usa_list}

# --- 3. CRIAÇÃO DAS ABAS ---
aba_macro, aba_br, aba_usa, aba_fundamentos = st.tabs(["🌍 Visão Macro", "🇧🇷 Ações Brasil", "🇺🇸 Ações EUA", "📊 Fundamentos & Valuation"])

def renderizar_grid_cards(dicionario_ativos, mercado):
    lista_tickers = [info[0] for info in dicionario_ativos.values()]
    dados_lote, fonte = buscar_dados_em_lote(lista_tickers, mercado)
    hora_consulta = datetime.now().strftime("%H:%M")
    
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
                                fig = go.Figure(go.Scatter(x=precos.index, y=precos, mode='lines', line=dict(color=cor_linha, width=2), fill='tozeroy', fillcolor=cor_preenchimento))
                                fig.update_layout(template="plotly_dark", height=80, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, showlegend=False, plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
                                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
                                st.caption(f"⚡ {hora_consulta} | {fonte}")

with aba_macro: renderizar_grid_cards(macro_dict, "Macro")
with aba_br: renderizar_grid_cards(acoes_br_dict, "BR")
with aba_usa: renderizar_grid_cards(acoes_usa_dict, "USA")

# --- 4. ABA DE FUNDAMENTOS E VALUATION ---
with aba_fundamentos:
    st.header("Radar de Valor e Qualidade (Fase 2)")
    
    arquivo_csv = "base_dados.csv"
    if os.path.exists(arquivo_csv):
        df = pd.read_csv(arquivo_csv, sep=";")
        
        # --- PAINEL DE CONTROLE DCF INTELIGENTE ---
        with st.expander("⚙️ Controles de Projeção DCF e Filtros", expanded=True):
            col_mercado, col_br, col_usa = st.columns([1, 1, 1])
            mercado = col_mercado.radio("Mercado Alvo:", ["Todos", "Ações Brasil", "Ações EUA"])
            
            # Os sliders agora nascem cravados nas taxas reais capturadas pelas APIs!
            taxa_juros_br = col_br.slider(f"Selic Atual BCB (%)", 4.0, 18.0, float(taxa_selic_live), 0.25, help="Taxa Básica de Juros do Brasil (Ao Vivo)")
            taxa_juros_usa = col_usa.slider(f"Treasury 10Y Atual (%)", 1.0, 10.0, float(taxa_us10y_live), 0.10, help="Título de 10 Anos dos EUA (Ao Vivo)")

        # --- FASE 1: VALUATIONS CLÁSSICOS ---
        df['Dividendo_Pago'] = df['Preco'] * (df['Div_Yield_%'] / 100)
        df['Teto_Bazin'] = df['Dividendo_Pago'] / 0.06
        df['Margem_Bazin_%'] = np.where(df['Teto_Bazin'] > 0, ((df['Teto_Bazin'] - df['Preco']) / df['Preco']) * 100, 0)
        
        df['Justo_Graham'] = np.where((df['LPA'] > 0) & (df['VPA'] > 0), np.sqrt(22.5 * df['LPA'] * df['VPA']), 0)
        df['Margem_Graham_%'] = np.where(df['Justo_Graham'] > 0, ((df['Justo_Graham'] - df['Preco']) / df['Preco']) * 100, 0)

        # --- FASE 2: F-SCORE, MÁGICA E DCF ---
        df['F_Score'] = 0
        df.loc[df['ROE_%'] > 0, 'F_Score'] += 1
        df.loc[df['Margem_Liquida_%'] > 5, 'F_Score'] += 1
        df.loc[df['Liquidez_Corrente'] > 1.2, 'F_Score'] += 1
        df.loc[df['Crescimento_5a_%'] > 0, 'F_Score'] += 1
        df.loc[df['LPA'] > 0, 'F_Score'] += 1
        df['Saude_Visual'] = df['F_Score'].apply(lambda x: "⭐" * int(x))

        mask_magica = (df['EV_EBIT'] > 0) & (df['ROIC_%'] > 0)
        df.loc[mask_magica, 'Rank_ROIC'] = df.loc[mask_magica, 'ROIC_%'].rank(ascending=False)
        df.loc[mask_magica, 'Rank_EV_EBIT'] = df.loc[mask_magica, 'EV_EBIT'].rank(ascending=True)
        df.loc[mask_magica, 'Pontuacao_Magica'] = df['Rank_ROIC'] + df['Rank_EV_EBIT']

        df['Taxa_Aplicada'] = np.where(df['Origem'].str.contains("BRAPI|Fundamentus"), taxa_juros_br, taxa_juros_usa)
        
        df['Crescimento_Limitado'] = df['Crescimento_5a_%'].clip(lower=0, upper=15)
        df['Justo_DCF'] = np.where(df['LPA'] > 0, df['LPA'] * (8.5 + 2 * df['Crescimento_Limitado']) * (4.4 / df['Taxa_Aplicada']), 0)
        df['Margem_DCF_%'] = np.where(df['Justo_DCF'] > 0, ((df['Justo_DCF'] - df['Preco']) / df['Preco']) * 100, 0)

        # --- RANKING DE CONVERGÊNCIA ---
        df['Rank_Bazin'] = df['Margem_Bazin_%'].rank(ascending=False)
        df['Rank_Graham'] = df['Margem_Graham_%'].rank(ascending=False)
        df['Rank_DCF'] = df['Margem_DCF_%'].rank(ascending=False)
        
        df['Nota_Convergencia'] = df['Rank_Bazin'] + df['Rank_Graham'] + df['Rank_DCF'] + df['Pontuacao_Magica'] - (df['F_Score'] * 10)
        
        df_exibir = df.copy()
        if mercado == "Ações Brasil": df_exibir = df_exibir[df_exibir['Origem'].str.contains("BRAPI|Fundamentus", na=False)]
        elif mercado == "Ações EUA": df_exibir = df_exibir[df_exibir['Origem'].str.contains("Finnhub|Yahoo", na=False)]
        
        df_exibir = df_exibir.sort_values(by='Nota_Convergencia', ascending=True)
        df_exibir.reset_index(drop=True, inplace=True)
        df_exibir.index = df_exibir.index + 1
        df_exibir['Rank_Geral'] = df_exibir.index.astype(str) + "º"

        # --- FORMATAÇÃO VISUAL ---
        colunas_dinheiro = ['Preco', 'Teto_Bazin', 'Justo_Graham', 'Justo_DCF']
        def formatar_moeda(linha, nome_coluna):
            valor = linha[nome_coluna]
            if pd.isna(valor) or valor == 0: return "N/A"
            simbolo = "R$" if "Fundamentus" in str(linha['Origem']) else "$"
            return f"{simbolo} {valor:.2f}"

        for col in colunas_dinheiro:
            df_exibir[col] = df_exibir.apply(lambda row: formatar_moeda(row, col), axis=1)
            
        colunas_percentuais = ['Margem_Bazin_%', 'Margem_Graham_%', 'Margem_DCF_%']
        for col in colunas_percentuais:
            df_exibir[col] = df_exibir[col].apply(lambda x: f"{x:.2f}%" if pd.notnull(x) and x != 0 else "N/A")

        colunas_exibicao = [
            'Rank_Geral', 'Ticker', 'Preco', 'Saude_Visual',
            'Teto_Bazin', 'Justo_Graham', 'Justo_DCF', 
            'Margem_Bazin_%', 'Margem_Graham_%', 'Margem_DCF_%'
        ]
        
        st.dataframe(df_exibir[colunas_exibicao], use_container_width=True, hide_index=True)
        
        data_modificacao = datetime.fromtimestamp(os.path.getmtime(arquivo_csv)).strftime("%d/%m/%Y %H:%M:%S")
        st.caption(f"🗄️ Base gerada em: {data_modificacao} | Taxas macroeconômicas atualizadas automaticamente via Banco Central e YF.")
    else:
        st.warning("⚠️ Banco de dados não encontrado. Execute 'robo_balancos.py' para gerar.")
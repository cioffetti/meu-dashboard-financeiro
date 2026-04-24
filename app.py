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

# --- MOTOR AUTÔNOMO DE TAXAS MACRO ---
@st.cache_data(ttl=3600)
def buscar_taxas_macro():
    selic_atual = 10.50
    us10y_atual = 4.25
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

# --- 2. LISTAS DE ATIVOS (100% RESTAURADAS) ---
macro_dict = {"Dólar": ("USDBRL=X", 3), "Euro": ("EURBRL=X", 3), "Ouro": ("GC=F", 2), "Petróleo (Brent)": ("BZ=F", 2), "Bitcoin": ("BTC-USD", 2), "Ethereum": ("ETH-USD", 2), "Solana": ("SOL-USD", 2), "Ibovespa": ("^BVSP", 2), "S&P 500": ("^GSPC", 2), "Dow Jones": ("^DJI", 2), "Nasdaq": ("^IXIC", 2), "DAX (Alem)": ("^GDAXI", 2), "Nikkei (Jap)": ("^N225", 2), "Shanghai (Chi)": ("000001.SS", 2), "Shenzhen (Chi)": ("399001.SZ", 2), "Merval (Arg)": ("^MERV", 2)}
acoes_br_list = ["AGRO3.SA", "AMOB3.SA", "BBAS3.SA", "BBDC3.SA", "BBSE3.SA", "BRSR6.SA", "B3SA3.SA", "CMIG3.SA", "CXSE3.SA", "EGIE3.SA", "EQTL3.SA", "EZTC3.SA", "FLRY3.SA", "GMAT3.SA", "ITSA4.SA", "KEPL3.SA", "KLBN3.SA", "LEVE3.SA", "PETR3.SA", "PRIO3.SA", "PSSA3.SA", "RAIZ4.SA", "RANI3.SA", "SAPR4.SA", "SBFG3.SA", "SMTO3.SA", "SOJA3.SA", "SUZB3.SA", "TAEE11.SA", "TTEN3.SA", "VAMO3.SA", "VIVT3.SA", "WEGE3.SA", "ETHE11.SA", "GOLD11.SA", "QSOL11.SA", "QBTC11.SA"]
acoes_br_dict = {ticker.replace(".SA", ""): (ticker, 2) for ticker in acoes_br_list}
acoes_usa_list = ["GOOGL", "AMZN", "NVDA", "TSM", "ASML", "AVGO", "IRS", "TSLA", "MU", "VZ", "T", "HD", "SHOP", "DIS", "SPG", "ANET", "ICE", "KO", "EQNR", "EPR", "WFC", "VICI", "O", "CPRT", "ASX", "CEPU", "NVO", "PLTR", "JBL", "QCOM", "AAPL", "MSFT", "BAC", "ORCL", "EQT", "MNST", "CVS", "HUYA", "GPC", "PFE", "ROKU", "DIBS", "LEG", "MBUU", "FVRR"]
acoes_usa_dict = {ticker: (ticker, 2) for ticker in acoes_usa_list}

# --- 3. CRIAÇÃO DAS ABAS ---
aba_macro, aba_br, aba_usa, aba_fundamentos, aba_simulador = st.tabs(["🌍 Visão Macro", "🇧🇷 Ações Brasil", "🇺🇸 Ações EUA", "📊 Fundamentos & Valuation", "🎛️ Simulador"])

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

# --- PREPARAÇÃO DOS DADOS BASE ---
arquivo_csv = "base_dados.csv"
if os.path.exists(arquivo_csv):
    df = pd.read_csv(arquivo_csv, sep=";")
    
    # Valuations Universais
    df['Dividendo_Pago'] = df['Preco'] * (df['Div_Yield_%'] / 100)
    df['Teto_Bazin'] = df['Dividendo_Pago'] / 0.06
    df['Margem_Bazin_%'] = np.where(df['Teto_Bazin'] > 0, ((df['Teto_Bazin'] - df['Preco']) / df['Preco']) * 100, 0)
    
    df['Justo_Graham'] = np.where((df['LPA'] > 0) & (df['VPA'] > 0), np.sqrt(22.5 * df['LPA'] * df['VPA']), 0)
    df['Margem_Graham_%'] = np.where(df['Justo_Graham'] > 0, ((df['Justo_Graham'] - df['Preco']) / df['Preco']) * 100, 0)

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

    # --- 4. ABA DE FUNDAMENTOS (RESTAURADA INTACTA) ---
    with aba_fundamentos:
        st.header("Radar de Valor e Qualidade (Fase 2)")
        
        with st.expander("⚙️ Controles de Projeção DCF e Filtros", expanded=True):
            col_mercado, col_br, col_usa = st.columns([1, 1, 1])
            mercado = col_mercado.radio("Mercado Alvo:", ["Todos", "Ações Brasil", "Ações EUA"], key="radio_fundamentos")
            taxa_juros_br = col_br.slider(f"Selic Atual BCB (%)", 4.0, 18.0, float(taxa_selic_live), 0.25, key="selic_fundamentos")
            taxa_juros_usa = col_usa.slider(f"Treasury 10Y Atual (%)", 1.0, 10.0, float(taxa_us10y_live), 0.10, key="us10_fundamentos")

        df_fundo = df.copy()
        df_fundo['Taxa_Aplicada'] = np.where(df_fundo['Origem'].str.contains("BRAPI|Fundamentus"), taxa_juros_br, taxa_juros_usa)
        
        df_fundo['Crescimento_Limitado'] = df_fundo['Crescimento_5a_%'].clip(lower=0, upper=15)
        df_fundo['Justo_DCF'] = np.where(df_fundo['LPA'] > 0, df_fundo['LPA'] * (8.5 + 2 * df_fundo['Crescimento_Limitado']) * (4.4 / df_fundo['Taxa_Aplicada']), 0)
        df_fundo['Margem_DCF_%'] = np.where(df_fundo['Justo_DCF'] > 0, ((df_fundo['Justo_DCF'] - df_fundo['Preco']) / df_fundo['Preco']) * 100, 0)

        df_fundo['Rank_Bazin'] = df_fundo['Margem_Bazin_%'].rank(ascending=False)
        df_fundo['Rank_Graham'] = df_fundo['Margem_Graham_%'].rank(ascending=False)
        df_fundo['Rank_DCF'] = df_fundo['Margem_DCF_%'].rank(ascending=False)
        
        df_fundo['Nota_Convergencia'] = df_fundo['Rank_Bazin'] + df_fundo['Rank_Graham'] + df_fundo['Rank_DCF'] + df_fundo['Pontuacao_Magica'] - (df_fundo['F_Score'] * 10)
        
        if mercado == "Ações Brasil": df_fundo = df_fundo[df_fundo['Origem'].str.contains("BRAPI|Fundamentus", na=False)]
        elif mercado == "Ações EUA": df_fundo = df_fundo[df_fundo['Origem'].str.contains("Finnhub|Yahoo", na=False)]
        
        df_fundo = df_fundo.sort_values(by='Nota_Convergencia', ascending=True)
        df_fundo.reset_index(drop=True, inplace=True)
        df_fundo.index = df_fundo.index + 1
        df_fundo['Rank_Geral'] = df_fundo.index.astype(str) + "º"

        colunas_dinheiro = ['Preco', 'Teto_Bazin', 'Justo_Graham', 'Justo_DCF']
        def formatar_moeda(linha, nome_coluna):
            valor = linha[nome_coluna]
            if pd.isna(valor) or valor == 0: return "N/A"
            simbolo = "R$" if "Fundamentus" in str(linha['Origem']) else "$"
            return f"{simbolo} {valor:.2f}"

        for col in colunas_dinheiro:
            df_fundo[col] = df_fundo.apply(lambda row: formatar_moeda(row, col), axis=1)
            
        colunas_percentuais = ['Margem_Bazin_%', 'Margem_Graham_%', 'Margem_DCF_%', 'ROIC_%']
        for col in colunas_percentuais:
            df_fundo[col] = df_fundo[col].apply(lambda x: f"{x:.2f}%" if pd.notnull(x) and x != 0 else "N/A")

        colunas_exibicao = [
            'Rank_Geral', 'Ticker', 'Preco', 'Saude_Visual', 'ROIC_%', 'EV_EBIT',
            'Teto_Bazin', 'Justo_Graham', 'Justo_DCF', 
            'Margem_Bazin_%', 'Margem_Graham_%', 'Margem_DCF_%'
        ]
        
        st.dataframe(df_fundo[colunas_exibicao], use_container_width=True, hide_index=True)

    # --- 5. ABA SIMULADOR (NOVA E ISOLADA) ---
    with aba_simulador:
        st.header("🎛️ Laboratório de Estratégia Ponderada")
        
        with st.expander("Defina seus Pesos de Decisão (0 a 100%)", expanded=True):
            c1, c2, c3, c4, c5 = st.columns(5)
            w_graham = c1.slider("Valor (Graham)", 0, 100, 20)
            w_bazin = c2.slider("Renda (Bazin)", 0, 100, 20)
            w_magic = c3.slider("Qualidade (Magic)", 0, 100, 20)
            w_fscore = c4.slider("Saúde (F-Score)", 0, 100, 20)
            w_dcf = c5.slider("Futuro (DCF)", 0, 100, 20)
            st.caption("O Simulador utiliza as taxas Selic e US10Y automáticas (ao vivo) para o cálculo do DCF.")

        df_sim = df.copy()
        
        # DCF Interno do Simulador
        df_sim['Taxa_Aplicada'] = np.where(df_sim['Origem'].str.contains("BRAPI|Fundamentus"), taxa_selic_live, taxa_us10y_live)
        df_sim['Crescimento_Limitado'] = df_sim['Crescimento_5a_%'].clip(lower=0, upper=15)
        df_sim['Justo_DCF'] = np.where(df_sim['LPA'] > 0, df_sim['LPA'] * (8.5 + 2 * df_sim['Crescimento_Limitado']) * (4.4 / df_sim['Taxa_Aplicada']), 0)
        df_sim['Margem_DCF_%'] = np.where(df_sim['Justo_DCF'] > 0, ((df_sim['Justo_DCF'] - df_sim['Preco']) / df_sim['Preco']) * 100, 0)

        # Normalização (0 a 100) baseada nos dados reais
        df_sim['N_Graham'] = df_sim['Margem_Graham_%'].rank(pct=True) * 100
        df_sim['N_Bazin'] = df_sim['Margem_Bazin_%'].rank(pct=True) * 100
        df_sim['N_DCF'] = df_sim['Margem_DCF_%'].rank(pct=True) * 100
        df_sim['N_Magic'] = df_sim.get('Pontuacao_Magica', pd.Series([0]*len(df_sim))).rank(ascending=False, pct=True) * 100
        df_sim['N_FScore'] = (df_sim['F_Score'] / 5) * 100

        total_w = w_graham + w_bazin + w_magic + w_fscore + w_dcf
        if total_w > 0:
            df_sim['Nota_Final'] = ((df_sim['N_Graham'] * w_graham) + (df_sim['N_Bazin'] * w_bazin) + (df_sim['N_Magic'].fillna(0) * w_magic) + (df_sim['N_FScore'] * w_fscore) + (df_sim['N_DCF'] * w_dcf)) / total_w
        else: df_sim['Nota_Final'] = 0

        df_sim = df_sim.sort_values(by='Nota_Final', ascending=False)
        df_sim.reset_index(drop=True, inplace=True)
        df_sim.index = df_sim.index + 1
        df_sim['Rank'] = df_sim.index.astype(str) + "º"
        
        df_sim['Veredito'] = pd.cut(df_sim['Nota_Final'], bins=[-1, 40, 75, 100], labels=["Neutro", "Estudo", "Compra Forte"])
        df_sim['Nota_Final'] = df_sim['Nota_Final'].apply(lambda x: f"{x:.1f}/100")

        def formatar_sim_moeda(linha):
            simbolo = "R$" if "Fundamentus" in str(linha['Origem']) else "$"
            return f"{simbolo} {linha['Preco']:.2f}"
        
        df_sim['Preco_Atual'] = df_sim.apply(formatar_sim_moeda, axis=1)

        st.dataframe(df_sim[['Rank', 'Ticker', 'Preco_Atual', 'Nota_Final', 'Veredito', 'Saude_Visual']], use_container_width=True, hide_index=True)

else: st.warning("⚠️ Banco de dados não encontrado. Execute 'robo_balancos.py' para gerar.")
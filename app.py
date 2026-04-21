import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from datetime import datetime
import os

# 1. CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="Dashboard Macro Pro", layout="wide")
st.title("🏛️ Monitor Financeiro - Pro")

# --- FUNÇÕES ÚTEIS ---
def formatar_br(valor, casas):
    if pd.isna(valor) or valor is None: return "N/A"
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")

# Motor de Lote Otimizado
@st.cache_data(ttl=900)
def buscar_dados_em_lote(lista_tickers):
    tickers_str = " ".join(lista_tickers)
    try:
        dados = yf.download(tickers_str, period="7d", interval="1d", progress=False)
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

# --- 2. LISTAS DE ATIVOS ---
macro_dict = {
    "Dólar": ("USDBRL=X", 3), "Euro": ("EURBRL=X", 3),
    "Ouro": ("GC=F", 2), "Petróleo (Brent)": ("BZ=F", 2),
    "Bitcoin": ("BTC-USD", 2), "Ethereum": ("ETH-USD", 2), "Solana": ("SOL-USD", 2),
    "Ibovespa": ("^BVSP", 2), "S&P 500": ("^GSPC", 2), "Dow Jones": ("^DJI", 2),
    "Nasdaq": ("^IXIC", 2), "DAX (Alem)": ("^GDAXI", 2), "Nikkei (Jap)": ("^N225", 2),
    "Shanghai (Chi)": ("000001.SS", 2), "Shenzhen (Chi)": ("399001.SZ", 2), "Merval (Arg)": ("^MERV", 2)
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
aba_macro, aba_br, aba_usa, aba_fundamentos = st.tabs([
    "🌍 Visão Macro", "🇧🇷 Ações Brasil", "🇺🇸 Ações EUA", "📊 Fundamentos & Valuation"
])

def renderizar_grid_cards(dicionario_ativos):
    lista_tickers = [info[0] for info in dicionario_ativos.values()]
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
                                st.caption(f"⚡ Atualizado: {hora_consulta} | Fonte: YF")

with aba_macro: renderizar_grid_cards(macro_dict)
with aba_br: renderizar_grid_cards(acoes_br_dict)
with aba_usa: renderizar_grid_cards(acoes_usa_dict)

# --- 4. ABA DE FUNDAMENTOS E VALUATION ---
with aba_fundamentos:
    st.header("Radar de Valor e Qualidade")
    
    arquivo_csv = "base_dados.csv"
    
    if os.path.exists(arquivo_csv):
        # Lê o CSV
        df = pd.read_csv(arquivo_csv, sep=";")
        
        # 1. Cálculos de Valuation
        # Bazin: Dividendo Pago / 0.06
        df['Dividendo_Pago'] = df['Preco'] * (df['Div_Yield_%'] / 100)
        df['Teto_Bazin'] = df['Dividendo_Pago'] / 0.06
        
        # Graham: Raiz quadrada de (22.5 * LPA * VPA). Se LPA ou VPA for negativo, retorna 0.
        df['Justo_Graham'] = np.where((df['LPA'] > 0) & (df['VPA'] > 0), 
                                      np.sqrt(22.5 * df['LPA'] * df['VPA']), 
                                      0)
        
        # Margem de Segurança Graham (%)
        df['Margem_Graham_%'] = np.where(df['Justo_Graham'] > 0,
                                         ((df['Justo_Graham'] - df['Preco']) / df['Preco']) * 100,
                                         0)
        
       # 2. Arredondamento e formatação visual condicional (R$ ou $)
        colunas_dinheiro = ['Preco', 'LPA', 'VPA', 'Teto_Bazin', 'Justo_Graham']
        
        def formatar_moeda(linha, nome_coluna):
            valor = linha[nome_coluna]
            if pd.isna(valor): return "N/A"
            
            # Se a origem for Brasil, usa R$. Se for EUA, usa $
            simbolo = "R$" if "Fundamentus" in str(linha['Origem']) else "$"
            return f"{simbolo} {valor:.2f}"

        for col in colunas_dinheiro:
            # Aplica a função linha por linha verificando a origem
            df[col] = df.apply(lambda row: formatar_moeda(row, col), axis=1)
            
        colunas_percentuais = ['Div_Yield_%', 'ROE_%', 'ROIC_%', 'Margem_Graham_%']
        for col in colunas_percentuais:
            df[col] = df[col].apply(lambda x: f"{x:.2f}%" if pd.notnull(x) else "N/A")

        # 3. Filtros no Painel
        mercado = st.radio("Selecione o Mercado:", ["Todos", "Ações Brasil", "Ações EUA"], horizontal=True)
        
        df_exibir = df.copy()
        if mercado == "Ações Brasil":
            df_exibir = df_exibir[df_exibir['Origem'].str.contains("BRAPI|Fundamentus", na=False)]
        elif mercado == "Ações EUA":
            df_exibir = df_exibir[df_exibir['Origem'] == "Yahoo Finance"]

        # Organizar ordem das colunas para exibição
        colunas_exibicao = ['Ticker', 'Preco', 'Div_Yield_%', 'Teto_Bazin', 'Justo_Graham', 'Margem_Graham_%', 'ROE_%', 'ROIC_%', 'Origem']
        
        # 4. Exibir a Tabela Interativa
        st.dataframe(df_exibir[colunas_exibicao], use_container_width=True, hide_index=True)
        
        # Governança
        data_modificacao = datetime.fromtimestamp(os.path.getmtime(arquivo_csv)).strftime("%d/%m/%Y %H:%M:%S")
        st.caption(f"🗄️ Base de Balanços estática gerada em: {data_modificacao} | Atualize via robo_balancos.py")
        
    else:
        st.warning("⚠️ Banco de dados não encontrado. Por favor, execute o arquivo 'robo_balancos.py' no terminal para gerar a base de dados pela primeira vez.")
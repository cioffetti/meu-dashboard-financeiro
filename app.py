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
import google.generativeai as genai
import xml.etree.ElementTree as ET

# --- CONFIGURAÇÃO DE SEGURANÇA ---
load_dotenv()
BRAPI_KEY = st.secrets.get("BRAPI_KEY", os.getenv("BRAPI_KEY", ""))
FINNHUB_KEY = st.secrets.get("FINNHUB_KEY", os.getenv("FINNHUB_KEY", ""))
GOOGLE_API_KEY = st.secrets.get("GOOGLE_API_KEY", os.getenv("GOOGLE_API_KEY", ""))

if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)

# 1. CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="Terminal Financeiro Pro", layout="wide")
st.title("🏛️ Terminal de Inteligência Financeira")

def formatar_br(valor, casas):
    if pd.isna(valor) or valor is None: return "N/A"
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")

# --- MOTOR DE COTAÇÕES EM LOTE (CARDS DA PÁGINA INICIAL) ---
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
        fechamentos = pd.DataFrame(dados['Close']) if isinstance(dados['Close'], pd.Series) else dados['Close']
        if len(lista_tickers) == 1: fechamentos.columns = lista_tickers
        return fechamentos, "Yahoo Finance"
    except Exception:
        return None, "ERRO"

# --- O TRADUTOR DE PREÇOS AO VIVO ---
@st.cache_data(ttl=300)
def injetar_precos_ao_vivo(df_base):
    df_atualizado = df_base.copy()
    tickers_yf = []
    mapa_tickers = {}
    
    for t in df_atualizado['Ticker']:
        t_clean = str(t).strip()
        if t_clean[-1].isdigit() and not t_clean.endswith(".SA"):
            t_yf = f"{t_clean}.SA"
        else:
            t_yf = t_clean
        tickers_yf.append(t_yf)
        mapa_tickers[t_yf] = t_clean

    try:
        dados = yf.download(" ".join(tickers_yf), period="1d", progress=False)
        if 'Close' in dados:
            fechamentos = dados['Close']
            if isinstance(fechamentos, pd.Series): 
                fechamentos = pd.DataFrame({tickers_yf[0]: fechamentos})
                
            for t_yf in fechamentos.columns:
                serie_preco = fechamentos[t_yf].dropna()
                if not serie_preco.empty:
                    preco_live = float(serie_preco.iloc[-1])
                    t_original = mapa_tickers[t_yf]
                    df_atualizado.loc[df_atualizado['Ticker'] == t_original, 'Preco'] = preco_live
    except Exception:
        pass 
    return df_atualizado

# --- JANELAS DE GRÁFICOS E IA ---
@st.dialog("📈 Histórico de Longo Prazo (5 Anos)", width="large")
def abrir_historico_simples(ticker, nome):
    st.write(f"Carregando histórico de 5 anos para **{nome}** ({ticker})...")
    try:
        dados = yf.Ticker(ticker).history(period="5y")
        if dados.empty: return st.error("Sem dados.")
        fig = go.Figure(go.Scatter(x=dados.index, y=dados['Close'], fill='tozeroy', line=dict(color='#00FFCC', width=2), fillcolor='rgba(0, 255, 204, 0.1)'))
        fig.update_layout(template="plotly_dark", height=500, margin=dict(l=0, r=0, t=10, b=0), xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e: st.error(f"Erro: {e}")

def calcular_indicadores_tecnicos(df):
    df['SMA_20'] = df['Close'].rolling(window=20).mean()
    df['STD_20'] = df['Close'].rolling(window=20).std()
    df['Bollinger_Upper'] = df['SMA_20'] + (df['STD_20'] * 2)
    df['Bollinger_Lower'] = df['SMA_20'] - (df['STD_20'] * 2)
    df['EMA_12'] = df['Close'].ewm(span=12, adjust=False).mean()
    df['EMA_26'] = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = df['EMA_12'] - df['EMA_26']
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    return df

def encontrar_suportes_resistencias(df):
    suportes, resistencias = [], []
    df_recente = df.tail(250)
    for i in range(10, len(df_recente)-10):
        if df_recente['Low'].iloc[i] == min(df_recente['Low'].iloc[i-10:i+10]): suportes.append(df_recente['Low'].iloc[i])
        if df_recente['High'].iloc[i] == max(df_recente['High'].iloc[i-10:i+10]): resistencias.append(df_recente['High'].iloc[i])
    preco_atual = df_recente['Close'].iloc[-1]
    s_filt = sorted([s for s in suportes if s < preco_atual], reverse=True)[:3]
    r_filt = sorted([r for r in resistencias if r > preco_atual])[:3]
    return s_filt, r_filt

@st.dialog("🔬 Raio-X Técnico Profissional", width="large")
def abrir_raio_x(ticker):
    st.write(f"Buscando histórico de mercado para **{ticker}** e calculando algoritmos...")
    try:
        dados = yf.Ticker(ticker).history(period="5y")
        if dados.empty: return st.error("Sem dados.")
        df_tec = calcular_indicadores_tecnicos(dados)
        suportes, resistencias = encontrar_suportes_resistencias(df_tec)
        df_tec = df_tec.tail(250) 
        
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, row_heights=[0.6, 0.2, 0.2], vertical_spacing=0.05, specs=[[{"secondary_y": False}], [{"secondary_y": True}], [{"secondary_y": False}]])
        fig.add_trace(go.Candlestick(x=df_tec.index, open=df_tec['Open'], high=df_tec['High'], low=df_tec['Low'], close=df_tec['Close'], name='Preço'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_tec.index, y=df_tec['Bollinger_Upper'], line=dict(color='rgba(255,255,255,0.2)', width=1), name='Banda Sup'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_tec.index, y=df_tec['Bollinger_Lower'], line=dict(color='rgba(255,255,255,0.2)', width=1), fill='tonexty', fillcolor='rgba(255,255,255,0.05)', name='Banda Inf'), row=1, col=1)
        
        for s in suportes: fig.add_hline(y=s, line_dash="dash", line_color="green", annotation_text=f"Sup: {s:.2f}", row=1, col=1)
        for r in resistencias: fig.add_hline(y=r, line_dash="dash", line_color="red", annotation_text=f"Res: {r:.2f}", row=1, col=1)

        cores_macd = ['#00FFCC' if val >= 0 else '#FF4B4B' for val in df_tec['MACD_Hist']]
        fig.add_trace(go.Bar(x=df_tec.index, y=df_tec['Volume'], marker_color='rgba(255,255,255,0.05)', name='Volume'), row=2, col=1, secondary_y=False)
        fig.add_trace(go.Scatter(x=df_tec.index, y=df_tec['MACD'], line=dict(color='blue', width=1.5), name='MACD'), row=2, col=1, secondary_y=True)
        fig.add_trace(go.Scatter(x=df_tec.index, y=df_tec['MACD_Signal'], line=dict(color='orange', width=1.5), name='Sinal'), row=2, col=1, secondary_y=True)
        fig.add_trace(go.Bar(x=df_tec.index, y=df_tec['MACD_Hist'], marker_color=cores_macd, name='Histograma'), row=2, col=1, secondary_y=True)

        fig.add_trace(go.Scatter(x=df_tec.index, y=df_tec['RSI'], line=dict(color='purple', width=2), name='RSI'), row=3, col=1)
        fig.add_hline(y=70, line_dash="dot", line_color="red", row=3, col=1)
        fig.add_hline(y=30, line_dash="dot", line_color="green", row=3, col=1)

        fig.update_layout(height=700, template="plotly_dark", showlegend=False, margin=dict(l=0, r=0, t=10, b=0), xaxis_rangeslider_visible=False, yaxis2=dict(showticklabels=False))
        st.plotly_chart(fig, use_container_width=True)
        
        rsi_atual = df_tec['RSI'].iloc[-1]
        preco_atual = df_tec['Close'].iloc[-1]
        st.markdown(f"**RSI Atual:** {rsi_atual:.1f} (Abaixo de 30 = Sobrevendido / Acima de 70 = Sobrecomprado)")
        if suportes:
            distancia = ((preco_atual - suportes[0]) / preco_atual) * 100
            st.markdown(f"**Distância para o Piso Seguro:** Faltam {distancia:.2f}% de queda para atingir o suporte gráfico mais próximo.")
            moeda = "R$" if ".SA" in ticker else "US$"
            st.success(f"🎯 **Preço Atrativo de Entrada:** {moeda} {suportes[0]:.2f}")
    except Exception as e: st.error(f"Erro: {e}")

@st.dialog("🧠 Parecer do Analista IA (Qualitativo)", width="large")
def gerar_relatorio_ia(ticker, dados_fundos=None):
    if not GOOGLE_API_KEY: return st.error("⚠️ Configure sua GOOGLE_API_KEY.")
    st.info(f"Coletando notícias reais e cruzando Pilares Institucionais para **{ticker}**...")
    
    try:
        data_balanco_str = "Recente"
        try:
            ativo_yf = yf.Ticker(ticker)
            info = ativo_yf.info
            if 'mostRecentQuarter' in info and info['mostRecentQuarter'] is not None:
                data_balanco_str = datetime.fromtimestamp(info['mostRecentQuarter']).strftime('%m/%Y')
            else:
                q_fin = ativo_yf.quarterly_financials
                if not q_fin.empty:
                    data_balanco_str = q_fin.columns[0].strftime('%m/%Y')
        except Exception:
            pass

        preco_atual_ia, suporte_ia = "N/A", "N/A"
        moeda_ia = "R$" if ".SA" in ticker else "US$"
        try:
            dados_hist = ativo_yf.history(period="2y")
            if not dados_hist.empty:
                df_tec_ia = calcular_indicadores_tecnicos(dados_hist)
                sup_ia, _ = encontrar_suportes_resistencias(df_tec_ia)
                if sup_ia: suporte_ia = f"{moeda_ia} {sup_ia[0]:.2f}"
                preco_atual_ia = f"{moeda_ia} {df_tec_ia['Close'].iloc[-1]:.2f}"
        except Exception: pass

        is_usa = ".SA" not in ticker
        texto_noticias = ""
        noticias_validas = []
        try:
            noticias_yf = ativo_yf.news
            if noticias_yf:
                for n in noticias_yf:
                    if not n.get('title'): continue
                    ts = n.get('providerPublishTime')
                    dt_pub = datetime.fromtimestamp(ts).strftime('%d/%m/%Y') if ts else "Recente"
                    fonte = n.get('publisher', 'Mercado')
                    noticias_validas.append(f"- Data: {dt_pub} | Fonte: {fonte} | Título: {n.get('title')}\n")
        except Exception: pass

        if len(noticias_validas) > 5:
            texto_noticias = "".join(noticias_validas[:30])
        else:
            termo_busca = ticker.replace(".SA", "")
            params = "hl=en-US&gl=US&ceid=US:en" if is_usa else "hl=pt-BR&gl=BR&ceid=BR:pt-419"
            url_news = f"https://news.google.com/rss/search?q={termo_busca}+stock+market&{params}" if is_usa else f"https://news.google.com/rss/search?q={termo_busca}+ação+mercado&{params}"
            try:
                resp = requests.get(url_news, timeout=10)
                if resp.status_code == 200:
                    root = ET.fromstring(resp.text)
                    for item in root.findall('.//item')[:30]:
                        t = item.find('title').text if item.find('title') is not None else ""
                        d = item.find('pubDate').text[5:16] if item.find('pubDate') is not None else "Recente"
                        f = item.find('source').text if item.find('source') is not None else "Portal Financeiro"
                        if t: texto_noticias += f"- Data: {d} | Fonte: {f} | Título: {t}\n"
            except Exception: pass
                
        if not texto_noticias.strip(): texto_noticias = "Sem notícias recentes mapeadas nas fontes globais e locais."

        contexto_dados = f"""
        **DADOS TÉCNICOS (PREÇO ATUAL E GRÁFICO):**
        - Preço Atual da Ação: {preco_atual_ia}
        - Suporte Gráfico (Preço Alvo Técnico): {suporte_ia}
        """
        
        metodo_val = "Desconhecido"
        if dados_fundos:
            v_pessimista = dados_fundos.get('Val_Pessimista', 0)
            v_base = dados_fundos.get('Val_Base', 0)
            v_otimista = dados_fundos.get('Val_Otimista', 0)
            v_fscore = dados_fundos.get('F_Score', 'N/A')
            v_roic = dados_fundos.get('ROIC_%', 'N/A')
            n_analistas = dados_fundos.get('Num_Analistas', 0)
            recomendacao = dados_fundos.get('Recomendacao', 'N/A')
            metodo_val = dados_fundos.get('Metodo_Valuation', 'Desconhecido')
            
            contexto_dados += f"""
        **VALUATION (METODOLOGIA APLICADA: {metodo_val}):**
        - Alvo Pessimista: {moeda_ia} {v_pessimista if isinstance(v_pessimista, str) else f"{v_pessimista:.2f}"}
        - Alvo Base (Preço Justo Central): {moeda_ia} {v_base if isinstance(v_base, str) else f"{v_base:.2f}"}
        - Alvo Otimista: {moeda_ia} {v_otimista if isinstance(v_otimista, str) else f"{v_otimista:.2f}"}
        - Cobertura: {n_analistas} analistas acompanham este ativo.
        - Recomendação Média: {recomendacao}
        
        **FUNDAMENTOS (NÃO CITE ESTES NÚMEROS DIRETAMENTE NO TEXTO):**
        - Qualidade F-Score: {v_fscore} de 5 estrelas.
        - Eficiência ROIC: {v_roic}%
            """

        data_hoje = datetime.now().strftime("%d/%m/%Y")

        prompt = f"""
        Hoje é dia {data_hoje}. Atue como o Analista Chefe do comitê de investimentos. 
        Analise o ativo {ticker}.
        
        Abaixo estão os Alvos de Valuation e as notícias REAIS coletadas:
        {contexto_dados}
        
        MANCHETES:
        {texto_noticias}
        
        REGRA DE FORMATAÇÃO E ESTILO (INEGOCIÁVEL):
        1. NÃO utilize o símbolo de cifrão ($) solto. Escreva sempre 'US$' ou 'R$'.
        2. Na Matriz SWOT, você DEVE fornecer EXATAMENTE 3 tópicos com marcadores (*) para cada categoria.
        3. Nas Notícias, pule uma linha entre a Manchete e o 'Resumo do Analista'.
        4. Avalie com extremo ceticismo se a empresa estiver 'Sem Cobertura' de mercado.
        
        A sua resposta DEVE seguir estritamente a estrutura abaixo:
        
        ## 1. Análise SWOT Dinâmica
        **Forças:**
        * [Ponto forte 1]
        * [Ponto forte 2]
        * [Ponto forte 3]
        
        **Fraquezas:**
        * [Ponto fraco 1]
        * [Ponto fraco 2]
        * [Ponto fraco 3]
        
        **Oportunidades:**
        * [Oportunidade 1]
        * [Oportunidade 2]
        * [Oportunidade 3]
        
        **Ameaças:**
        * [Ameaça 1]
        * [Ameaça 2]
        * [Ameaça 3]
        
        ## 2. Raio-X do Balanço (Foco Operacional - Referência: Balanço de {data_balanco_str})
        REGRA RIGOROSA: NÃO mencione as palavras "F-Score", "ROIC", "Valuation", nem cite as notas matemáticas. Leia os fundamentos operacionais implícitos da empresa no mundo real com base em seu conhecimento da economia atual e das notícias.
        
        **Pontos Positivos:**
        * ✅ [Fato positivo real 1 sobre a operação/negócio]
        * ✅ [Fato positivo real 2 sobre a operação/negócio]
        * ✅ [Fato positivo real 3 sobre a operação/negócio]
        
        **Pontos de Atenção (Negativos):**
        * ⚠️ [Fato negativo/risco real 1 sobre a operação/negócio]
        * ⚠️ [Fato negativo/risco real 2 sobre a operação/negócio]
        * ⚠️ [Fato negativo/risco real 3 sobre a operação/negócio]
        
        ## 3. Termômetro de Notícias
        Selecione as 3 manchetes reais mais relevantes.
        
        **Notícias Recentes:**
        * **[Data] - [Fonte] - [Manchete]**
        
          **Resumo do Analista:** [Explicação fluida e separada da manchete].
        
        * **[Data] - [Fonte] - [Manchete]**
        
          **Resumo do Analista:** [Explicação fluida e separada da manchete].
          
        * **[Data] - [Fonte] - [Manchete]**
        
          **Resumo do Analista:** [Explicação fluida e separada da manchete].
        
        ---
        ## 4. O Quadrante de Decisão
        * 📈 **Análise Gráfica (Timing):** [Aprove ou rejeite a entrada com base no Suporte Técnico fornecido em relação ao preço atual].
        * 💰 **Valuation ({metodo_val}):** [Avalie o preço atual frente ao Cenário Base fornecido. O ativo embute prêmio de risco adequado ou negocia com margem?].
        * 🏢 **Fundamentos:** [Escreva julgando a saúde e resiliência da empresa].
        * 🌡️ **Sentimento de Mercado:** [Defina em caixa alta OTIMISTA, NEUTRO ou PESSIMISTA, e escreva justificando com base nas notícias].
        
        ## 👑 Veredito Final
        **Ação Recomendada:** [COMPRAR, MANTER, AGUARDAR SUPORTE ou VENDER].
        
        **Preço Sugerido para Compra:** [Com base no Suporte Gráfico e no Preço Alvo Base, defina o preço teto exato de entrada].
        
        **Tese Final:** [Escreva o fechamento da análise cruzando o preço técnico, o valuation, os fundamentos e a narrativa da mídia].
        """
        
        model = genai.GenerativeModel('gemini-2.5-flash-lite')
        response = model.generate_content(prompt)
        st.markdown(response.text)
    except Exception as e:
        st.error(f"Erro ao comunicar com a IA ou processar dados: {e}")

# --- LISTAS DE ATIVOS ---
macro_dict = {"Dólar": ("USDBRL=X", 3), "Euro": ("EURBRL=X", 3), "Ouro": ("GC=F", 2), "Petróleo (Brent)": ("BZ=F", 2), "Bitcoin": ("BTC-USD", 2), "Ethereum": ("ETH-USD", 2), "Solana": ("SOL-USD", 2), "Ibovespa": ("^BVSP", 2), "S&P 500": ("^GSPC", 2), "Dow Jones": ("^DJI", 2), "Nasdaq": ("^IXIC", 2), "DAX (Alem)": ("^GDAXI", 2), "Nikkei (Jap)": ("^N225", 2), "Shanghai (Chi)": ("000001.SS", 2), "Shenzhen (Chi)": ("399001.SZ", 2), "Merval (Arg)": ("^MERV", 2)}

acoes_br_list = ["AGRO3.SA", "AMOB3.SA", "BBAS3.SA", "BBDC3.SA", "BBSE3.SA", "BRSR6.SA", "B3SA3.SA", "CMIG3.SA", "CXSE3.SA", "EGIE3.SA", "EQTL3.SA", "EZTC3.SA", "FLRY3.SA", "GMAT3.SA", "ITSA4.SA", "KEPL3.SA", "KLBN3.SA", "LEVE3.SA", "PETR3.SA", "PRIO3.SA", "PSSA3.SA", "RAIZ4.SA", "RANI3.SA", "SAPR4.SA", "SBFG3.SA", "SMTO3.SA", "SOJA3.SA", "SUZB3.SA", "TAEE11.SA", "TTEN3.SA", "VAMO3.SA", "VIVT3.SA", "WEGE3.SA", "ETHE11.SA", "GOLD11.SA", "QSOL11.SA", "QBTC11.SA"]
acoes_br_dict = {ticker.replace(".SA", ""): (ticker, 2) for ticker in acoes_br_list}

acoes_usa_list = ["GOOGL", "AMZN", "NVDA", "TSM", "ASML", "AVGO", "IRS", "TSLA", "MU", "VZ", "T", "HD", "SHOP", "DIS", "SPG", "ANET", "ICE", "KO", "EQNR", "EPR", "WFC", "VICI", "O", "CPRT", "ASX", "CEPU", "NVO", "PLTR", "JBL", "QCOM", "AAPL", "MSFT", "BAC", "ORCL", "EQT", "MNST", "CVS", "HUYA", "GPC", "PFE", "ROKU", "DIBS", "LEG", "MBUU", "FVRR"]
acoes_usa_dict = {ticker: (ticker, 2) for ticker in acoes_usa_list}

# --- CRIAÇÃO DAS ABAS ---
aba_macro, aba_br, aba_usa, aba_fundamentos, aba_valuation, aba_rankings, aba_simulador, aba_analises = st.tabs([
    "🌍 Visão Macro", "🇧🇷 Ações Brasil", "🇺🇸 Ações EUA", "📊 Fundamentos", "🧮 Valuation Pro", "🏆 Rankings", "🎛️ Simulador", "🎯 Raio-X & IA"
])

# --- RENDERIZAÇÃO DOS CARDS ---
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
                                if st.button("🔍 Histórico", key=f"btn_hist_{ticker}_{mercado}", use_container_width=True):
                                    abrir_historico_simples(ticker, nome_exibicao)
                                st.caption(f"⚡ {hora_consulta} | {fonte}")

with aba_macro: renderizar_grid_cards(macro_dict, "Macro")
with aba_br: renderizar_grid_cards(acoes_br_dict, "BR")
with aba_usa: renderizar_grid_cards(acoes_usa_dict, "USA")

# --- MOTOR DE DADOS CENTRAL ---
arquivo_csv = "base_dados.csv"
arquivo_cofre = "cofre_consenso.csv"
dados_base_carregados = False

if os.path.exists(arquivo_csv):
    df = pd.read_csv(arquivo_csv, sep=";")
    
    # Injeta Preços Fresquinhos
    df = injetar_precos_ao_vivo(df)
    dados_base_carregados = True
    
    # --- CÁLCULO DE TODOS OS ALVOS E MARGENS ---
    df['Dividendo_Pago'] = df['Preco'] * (df['Div_Yield_%'] / 100)
    df['Teto_Bazin'] = df['Dividendo_Pago'] / 0.06
    df['Margem_Bazin_%'] = np.where(df['Teto_Bazin'] > 0, ((df['Teto_Bazin'] - df['Preco']) / df['Preco']) * 100, 0)
    
    df['Justo_Graham'] = np.where((df['LPA'] > 0) & (df['VPA'] > 0), np.sqrt(22.5 * df['LPA'] * df['VPA']), 0)
    df['Margem_Graham_%'] = np.where(df['Justo_Graham'] > 0, ((df['Justo_Graham'] - df['Preco']) / df['Preco']) * 100, 0)

    # SOBERANIA DO COFRE DE CONSENSO
    if os.path.exists(arquivo_cofre):
        df_cofre = pd.read_csv(arquivo_cofre, sep=";")
        df_cofre = df_cofre.drop_duplicates(subset=['Ticker'], keep='last')
        df = pd.merge(df, df_cofre[['Ticker', 'Val_Pessimista', 'Val_Base', 'Val_Otimista', 'Num_Analistas', 'Recomendacao']], on='Ticker', how='left')
    
    for col in ['Val_Pessimista', 'Val_Base', 'Val_Otimista', 'Num_Analistas']:
        if col not in df.columns: df[col] = 0
        df[col] = df[col].fillna(0)
    
    if 'Recomendacao' not in df.columns: df['Recomendacao'] = 'N/A'
    df['Metodo_Valuation'] = np.where(df['Val_Base'] > 0, "Consenso Analistas", "Sem Cobertura")
    
    # MARGENS DE UPSIDE (CONSENSO)
    df['Margem_Pessimista_%'] = np.where(df['Val_Pessimista'] > 0, ((df['Val_Pessimista'] - df['Preco']) / df['Preco']) * 100, -999)
    df['Margem_Base_%'] = np.where(df['Val_Base'] > 0, ((df['Val_Base'] - df['Preco']) / df['Preco']) * 100, -999)
    df['Margem_Otimista_%'] = np.where(df['Val_Otimista'] > 0, ((df['Val_Otimista'] - df['Preco']) / df['Preco']) * 100, -999)

    # SAÚDE E QUALIDADE
    df['F_Score'] = 0
    df.loc[df['ROE_%'] > 0, 'F_Score'] += 1
    df.loc[df['Margem_Liquida_%'] > 5, 'F_Score'] += 1
    df.loc[df['Liquidez_Corrente'] > 1.2, 'F_Score'] += 1
    df.loc[df['Crescimento_5a_%'] > 0, 'F_Score'] += 1
    df.loc[df['LPA'] > 0, 'F_Score'] += 1
    df['Saude_Visual'] = df['F_Score'].apply(lambda x: "⭐" * int(x) if pd.notnull(x) and x > 0 else "Sem Nota")

    mask_magica = (df['EV_EBIT'] > 0) & (df['ROIC_%'] > 0)
    df.loc[mask_magica, 'Rank_ROIC'] = df.loc[mask_magica, 'ROIC_%'].rank(ascending=False)
    df.loc[mask_magica, 'Rank_EV_EBIT'] = df.loc[mask_magica, 'EV_EBIT'].rank(ascending=True)
    df.loc[mask_magica, 'Pontuacao_Magica'] = df['Rank_ROIC'] + df['Rank_EV_EBIT']

    # --- ABA DE RANKINGS DINÂMICOS (SCREENER) ---
    with aba_rankings:
        st.header("🏆 Rankings de Pechinchas (Screener)")
        st.write("Ações separadas por mercado para garantir comparabilidade justa de risco e prêmio.")

        filtro_metodo = st.selectbox(
            "Selecione a Metodologia (Ordenação):",
            ["Consenso Base (Média de Mercado)",
             "Consenso Pessimista (Conservador)",
             "Consenso Otimista (Cenário Azul)",
             "Teto de Bazin (Foco em Renda/Dividendos)",
             "Justo de Graham (Foco em Patrimônio/Lucro)",
             "Fórmula Mágica (Greenblatt - Foco em Qualidade e Preço)"]
        )

        df_rank = df.copy()

        if filtro_metodo == "Consenso Base (Média de Mercado)":
            col_alvo, col_margem = 'Val_Base', 'Margem_Base_%'
        elif filtro_metodo == "Consenso Pessimista (Conservador)":
            col_alvo, col_margem = 'Val_Pessimista', 'Margem_Pessimista_%'
        elif filtro_metodo == "Consenso Otimista (Cenário Azul)":
            col_alvo, col_margem = 'Val_Otimista', 'Margem_Otimista_%'
        elif filtro_metodo == "Teto de Bazin (Foco em Renda/Dividendos)":
            col_alvo, col_margem = 'Teto_Bazin', 'Margem_Bazin_%'
        elif filtro_metodo == "Justo de Graham (Foco em Patrimônio/Lucro)":
            col_alvo, col_margem = 'Justo_Graham', 'Margem_Graham_%'
        elif filtro_metodo == "Fórmula Mágica (Greenblatt - Foco em Qualidade e Preço)":
            col_alvo, col_margem = 'Pontuacao_Magica', 'Pontuacao_Magica'

        df_rank = df_rank[df_rank[col_alvo] > 0]

        def format_money(r, c):
            simb = "R$" if "Fundamentus" in str(r['Origem']) else "$"
            return f"{simb} {r[c]:.2f}"

        df_br = df_rank[df_rank['Origem'].str.contains("Fundamentus|BRAPI", na=False)].copy()
        df_usa = df_rank[~df_rank['Origem'].str.contains("Fundamentus|BRAPI", na=False)].copy()

        # Renderizador de Tabela HTML/CSS Personalizada
        def mostrar_tabela_ranking(df_sub, titulo):
            st.subheader(titulo)
            if df_sub.empty:
                st.info("Nenhum ativo atende aos critérios nesta métrica.")
                return
            
            asc = True if filtro_metodo == "Fórmula Mágica (Greenblatt - Foco em Qualidade e Preço)" else False
            df_sub = df_sub.sort_values(by=col_margem, ascending=asc).reset_index(drop=True)
            df_sub.index = df_sub.index + 1
            df_sub['Posição'] = df_sub.index.astype(str) + "º"
            
            html = """
            <style>
            .tabela-pro { width: 100%; border-collapse: collapse; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #1e1e1e; border-radius: 8px; overflow: hidden; margin-bottom: 20px;}
            .tabela-pro th { background-color: #151515; color: #ff9900; font-size: 11px; text-transform: uppercase; padding: 14px 12px; text-align: left; border-bottom: 2px solid #333; }
            .tabela-pro td { padding: 14px 12px; border-bottom: 1px solid #2b2b2b; color: #ecf0f1; font-size: 13px; }
            .tabela-pro tr:hover { background-color: #252525; }
            .tabela-ativo { color: #3498db; font-weight: bold; text-decoration: none; }
            .badge-ia { border: 1px solid #f1c40f; color: #f1c40f; padding: 3px 8px; border-radius: 4px; font-size: 10px; font-weight: bold; background: rgba(241, 196, 15, 0.05); }
            .val-positivo { color: #00cc66; font-weight: bold; }
            .val-neutro { color: #bdc3c7; }
            </style>
            <table class="tabela-pro">
              <thead>
                <tr>
                  <th>Posição</th>
                  <th>Ativo</th>
                  <th>Status IA</th>
                  <th>Preço Atual</th>
                  <th>Preço Alvo</th>
                  <th>Upside / Margem</th>
                  <th>Saúde Visual</th>
            """
            if "Consenso" in filtro_metodo:
                html += "<th>Analistas</th><th>Recomendação</th>"
            html += "</tr></thead><tbody>"

            for idx, row in df_sub.iterrows():
                preco_atual = format_money(row, 'Preco')
                
                if filtro_metodo == "Fórmula Mágica (Greenblatt - Foco em Qualidade e Preço)":
                    preco_alvo = "---"
                    upside_text = f"Score: {row['Pontuacao_Magica']:.0f}"
                    upside_class = "val-positivo"
                else:
                    preco_alvo = format_money(row, col_alvo)
                    upside_val = row[col_margem]
                    upside_text = f"+{upside_val:.2f}%" if upside_val > 0 else f"{upside_val:.2f}%"
                    upside_class = "val-positivo" if upside_val > 0 else "val-neutro"

                html += f"""
                <tr>
                  <td>{row['Posição']}</td>
                  <td class="tabela-ativo">{row['Ticker']}</td>
                  <td><span class="badge-ia">N/A</span></td>
                  <td>{preco_atual}</td>
                  <td>{preco_alvo}</td>
                  <td class="{upside_class}">{upside_text}</td>
                  <td>{row['Saude_Visual']}</td>
                """
                if "Consenso" in filtro_metodo:
                    html += f"<td>{row['Num_Analistas']}</td><td>{row['Recomendacao']}</td>"
                html += "</tr>"

            html += "</tbody></table>"
            st.markdown(html, unsafe_allow_html=True)

        mostrar_tabela_ranking(df_br, "🇧🇷 Top Oportunidades: Brasil")
        mostrar_tabela_ranking(df_usa, "🇺🇸 Top Oportunidades: Wall Street")

    # --- ABA DE VALUATION PRO ---
    with aba_valuation:
        st.header("🧮 Valuation Institucional (Puro Consenso)")
        
        df_cenarios = df.copy()
        def formata_val(linha, col):
            if pd.isna(linha[col]) or linha[col] <= 0: return "---"
            simb = "R$" if "Fundamentus" in str(linha['Origem']) else "$"
            return f"{simb} {linha[col]:.2f}"
            
        df_cenarios['Preco Atual'] = df_cenarios.apply(lambda r: f"{'R$' if 'Fundamentus' in str(r['Origem']) else '$'} {r['Preco']:.2f}", axis=1)
        df_cenarios['🔴 Alvo Pessimista'] = df_cenarios.apply(lambda r: formata_val(r, 'Val_Pessimista'), axis=1)
        df_cenarios['🟡 Alvo Base'] = df_cenarios.apply(lambda r: formata_val(r, 'Val_Base'), axis=1)
        df_cenarios['🟢 Alvo Otimista'] = df_cenarios.apply(lambda r: formata_val(r, 'Val_Otimista'), axis=1)
        df_cenarios = df_cenarios.sort_values(by='Margem_Base_%', ascending=False)
        
        st.dataframe(
            df_cenarios[['Ticker', 'Preco Atual', '🔴 Alvo Pessimista', '🟡 Alvo Base', '🟢 Alvo Otimista', 'Num_Analistas', 'Recomendacao', 'Metodo_Valuation']], 
            use_container_width=True, hide_index=True
        )

    # --- ABA DE FUNDAMENTOS ---
    with aba_fundamentos:
        st.header("Radar de Valor e Qualidade")
        
        df_fundo = df.copy().sort_values(by='Pontuacao_Magica', ascending=True)
        
        def formatar_moeda(linha, nome_coluna):
            valor = linha[nome_coluna]
            if pd.isna(valor) or valor <= 0: return "---"
            simbolo = "R$" if "Fundamentus" in str(linha['Origem']) else "$"
            return f"{simbolo} {valor:.2f}"

        for col in ['Preco', 'Teto_Bazin', 'Justo_Graham']:
            df_fundo[col] = df_fundo.apply(lambda row: formatar_moeda(row, col), axis=1)
            
        df_fundo['Pontuacao_Magica'] = df_fundo['Pontuacao_Magica'].apply(lambda x: f"{x:.0f}" if pd.notnull(x) and x > 0 else "---")
        df_fundo['ROIC_%'] = df_fundo['ROIC_%'].apply(lambda x: f"{x:.2f}%" if pd.notnull(x) else "---")
        df_fundo['ROE_%'] = df_fundo['ROE_%'].apply(lambda x: f"{x:.2f}%" if pd.notnull(x) else "---")
        df_fundo['EV_EBIT'] = df_fundo['EV_EBIT'].apply(lambda x: f"{x:.2f}" if pd.notnull(x) and x > 0 else "---")
        df_fundo['Div_Yield_%'] = df_fundo['Div_Yield_%'].apply(lambda x: f"{x:.2f}%" if pd.notnull(x) else "---")
        df_fundo['Crescimento_5a_%'] = df_fundo['Crescimento_5a_%'].apply(lambda x: f"{x:.2f}%" if pd.notnull(x) else "---")

        colunas_para_exibir = [
            'Ticker', 'Preco', 'Saude_Visual', 'F_Score', 'Pontuacao_Magica', 
            'ROIC_%', 'ROE_%', 'EV_EBIT', 'Div_Yield_%', 'Crescimento_5a_%', 
            'Teto_Bazin', 'Justo_Graham'
        ]
        
        st.dataframe(df_fundo[colunas_para_exibir], use_container_width=True, hide_index=True)

    # --- ABA SIMULADOR ---
    with aba_simulador:
        st.header("🎛️ Laboratório de Estratégia Ponderada")
        
        with st.expander("Defina seus Pesos de Decisão (0 a 100%)", expanded=True):
            c1, c2, c3, c4, c5 = st.columns(5)
            w_graham = c1.slider("Valor (Graham)", 0, 100, 20)
            w_bazin = c2.slider("Renda (Bazin)", 0, 100, 20)
            w_magic = c3.slider("Qualidade (Magic)", 0, 100, 20)
            w_fscore = c4.slider("Saúde (F-Score)", 0, 100, 20)
            w_dcf = c5.slider("Mercado (Consenso)", 0, 100, 20)

        df_sim = df.copy()
        df_sim['N_Graham'] = df_sim['Margem_Graham_%'].rank(pct=True) * 100
        df_sim['N_Bazin'] = df_sim['Margem_Bazin_%'].rank(pct=True) * 100
        
        df_sim['Margem_Temp_Mercado'] = np.where(df_sim['Margem_Base_%'] != -999, df_sim['Margem_Base_%'], 0)
        df_sim['N_Mercado'] = df_sim['Margem_Temp_Mercado'].rank(pct=True) * 100
        
        df_sim['N_Magic'] = df_sim.get('Pontuacao_Magica', pd.Series([0]*len(df_sim))).fillna(0).rank(ascending=False, pct=True) * 100
        df_sim['N_FScore'] = (df_sim['F_Score'] / 5) * 100

        total_w = w_graham + w_bazin + w_magic + w_fscore + w_dcf
        if total_w > 0:
            df_sim['Nota_Final'] = ((df_sim['N_Graham']*w_graham) + (df_sim['N_Bazin']*w_bazin) + (df_sim['N_Magic'].fillna(0)*w_magic) + (df_sim['N_FScore']*w_fscore) + (df_sim['N_Mercado']*w_dcf)) / total_w
        else: df_sim['Nota_Final'] = 0

        df_sim = df_sim.sort_values(by='Nota_Final', ascending=False).reset_index(drop=True)
        df_sim.index = df_sim.index + 1
        df_sim['Rank'] = df_sim.index.astype(str) + "º"
        df_sim['Veredito'] = pd.cut(df_sim['Nota_Final'], bins=[-1, 40, 75, 100], labels=["Neutro", "Estudo", "Compra Forte"])
        df_sim['Nota_Final'] = df_sim['Nota_Final'].apply(lambda x: f"{x:.1f}/100")
        
        df_sim['Preco_Atual'] = df_sim.apply(lambda r: f"{'R$' if 'Fundamentus' in str(r['Origem']) else '$'} {r['Preco']:.2f}", axis=1)
        st.dataframe(df_sim[['Rank', 'Ticker', 'Preco_Atual', 'Nota_Final', 'Veredito', 'Saude_Visual']], use_container_width=True, hide_index=True)

else: 
    st.warning("⚠️ Execute o 'robo_balancos.py' primeiro.")

# --- ABA DE ANÁLISES ---
with aba_analises:
    st.header("🎯 Central de Inteligência Profissional")
    col1, col2, col3 = st.columns([2, 1, 1])
    todos_ativos = [t for t in acoes_br_list + acoes_usa_list if "11.SA" not in t]
    ativo_selecionado = col1.selectbox("Escolha a Ação:", sorted(todos_ativos))
    
    if col2.button("📈 Abrir Raio-X Técnico", use_container_width=True): abrir_raio_x(ativo_selecionado)
    if col3.button("🧠 Gerar Veredito IA", use_container_width=True): 
        dados_envio = None
        if dados_base_carregados:
            t_limpo = ativo_selecionado.replace(".SA", "")
            linha = df[df['Ticker'].str.contains(t_limpo, na=False)]
            if not linha.empty: dados_envio = linha.iloc[0].to_dict()
        gerar_relatorio_ia(ativo_selecionado, dados_envio)
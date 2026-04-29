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

# --- CONFIGURAÇÃO DE SEGURANÇA HÍBRIDA ---
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
        return None, "ERRO"

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

# --- JANELA DE HISTÓRICO SIMPLES (5 ANOS) ---
@st.dialog("📈 Histórico de Longo Prazo (5 Anos)", width="large")
def abrir_historico_simples(ticker, nome):
    st.write(f"Carregando histórico de 5 anos para **{nome}** ({ticker})...")
    try:
        dados = yf.Ticker(ticker).history(period="5y")
        if dados.empty:
            st.error("Dados não encontrados para este ativo no Yahoo Finance.")
            return
            
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=dados.index, y=dados['Close'], fill='tozeroy', mode='lines', 
            line=dict(color='#00FFCC', width=2), fillcolor='rgba(0, 255, 204, 0.1)', name="Preço"
        ))
        fig.update_layout(
            template="plotly_dark", height=500, margin=dict(l=0, r=0, t=10, b=0), 
            xaxis_rangeslider_visible=False, yaxis_title="Cotação"
        )
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Erro ao carregar histórico: {e}")

# --- FASE 4: MOTOR DE INTELIGÊNCIA ARTIFICIAL (RAG INSTITUCIONAL HÍBRIDO) ---
@st.dialog("🧠 Parecer do Analista IA (Qualitativo)", width="large")
def gerar_relatorio_ia(ticker, dados_fundos=None):
    if not GOOGLE_API_KEY:
        st.error("⚠️ Chave GOOGLE_API_KEY não encontrada. Configure no arquivo .env.")
        return
        
    st.info(f"Coletando notícias reais e cruzando Pilares Institucionais para **{ticker}**...")
    
    try:
        preco_atual_ia = "N/A"
        suporte_ia = "N/A"
        moeda_ia = "R$" if ".SA" in ticker else "US$"
        try:
            dados_hist = yf.Ticker(ticker).history(period="2y")
            if not dados_hist.empty:
                df_tec_ia = calcular_indicadores_tecnicos(dados_hist)
                sup_ia, _ = encontrar_suportes_resistencias(df_tec_ia)
                suporte_ia = f"{moeda_ia} {sup_ia[0]:.2f}" if sup_ia else "Não identificado"
                preco_atual_ia = f"{moeda_ia} {df_tec_ia['Close'].iloc[-1]:.2f}"
        except Exception: pass

        is_usa = ".SA" not in ticker
        texto_noticias = ""
        noticias_validas = []
        try:
            noticias_yf = yf.Ticker(ticker).news
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
                    items = root.findall('.//item')
                    for item in items[:30]:
                        t = item.find('title').text if item.find('title') is not None else ""
                        d = item.find('pubDate').text[5:16] if item.find('pubDate') is not None else "Recente"
                        f = item.find('source').text if item.find('source') is not None else "Portal Financeiro"
                        if t: texto_noticias += f"- Data: {d} | Fonte: {f} | Título: {t}\n"
            except Exception: pass
                
        if not texto_noticias.strip():
            texto_noticias = "Sem notícias recentes mapeadas nas fontes globais e locais."

        contexto_dados = f"""
        **DADOS TÉCNICOS (PREÇO ATUAL E GRÁFICO):**
        - Preço Atual da Ação: {preco_atual_ia}
        - Suporte Gráfico (Preço Alvo Técnico): {suporte_ia}
        """
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
        - Cobertura: {n_analistas} analistas acompanham este ativo. (Se o número for 0, o valuation foi calculado matematicamente pelo terminal via DCF).
        - Recomendação Média: {recomendacao}
        
        **FUNDAMENTOS OPERACIONAIS:**
        - Nota de Qualidade da Empresa (F-Score): {v_fscore} de 5 estrelas.
        - ROIC Atual: {v_roic}%
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
        2. Na Matriz SWOT, você DEVE fornecer EXATAMENTE 3 tópicos para cada categoria.
        3. Nas Notícias, pule uma linha entre a Manchete e o 'Resumo do Analista'.
        4. Cuidado com falsos otimismos se o "Grau de Cobertura" for muito baixo ou se o Valuation for "DCF Matemático (Terminal)".
        
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
        
        ## 2. Raio-X do Balanço (Foco Operacional)
        REGRA: Avalie APENAS a qualidade da operação e a saúde (ROIC, Estrelas). É expressamente proibido citar fórmulas de valuation de gurus ou preços nesta seção.
        * **✅ 3 Pontos Positivos:** [Descreva 3 destaques da operação de forma fluida]
        * **⚠️ 3 Pontos de Atenção (Negativos):** [Descreva 3 preocupações operacionais/financeiras]
        
        ## 3. Termômetro de Notícias
        Selecione as 5 manchetes reais mais positivas e as 5 mais negativas. Ordene-as da mais RECENTE para a mais ANTIGA.
        
        **Notícias Positivas Recentes:**
        * **[Data] - [Fonte] - [Manchete]**
        
          **Resumo do Analista:** [Explicação fluida e separada da manchete].
        
        **Notícias Negativas Recentes:**
        * **[Data] - [Fonte] - [Manchete]**
        
          **Resumo do Analista:** [Explicação fluida e separada da manchete].
        
        ---
        ## 4. O Quadrante de Decisão
        * 📈 **Análise Gráfica (Timing):** [Aprove ou rejeite a entrada com base no Suporte Técnico fornecido em relação ao preço atual].
        * 💰 **Valuation ({metodo_val}):** [Avalie o preço atual frente ao Cenário Base fornecido. O ativo embute prêmio de risco adequado ou negocia com margem?].
        * 🏢 **Fundamentos:** [Escreva julgando a qualidade da operação com base nas Estrelas F-Score e no ROIC].
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

# --- MOTOR DE ANÁLISE TÉCNICA (FASE 3) ---
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
        if dados.empty:
            st.error("Dados não encontrados para este ativo no Yahoo Finance.")
            return
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
            st.success(f"🎯 **Preço Atrativo de Entrada (Suporte Mais Próximo):** {moeda} {suportes[0]:.2f}")
    except Exception as e: st.error(f"Erro ao processar Raio-X: {e}")

# --- LISTAS DE ATIVOS ---
macro_dict = {"Dólar": ("USDBRL=X", 3), "Euro": ("EURBRL=X", 3), "Ouro": ("GC=F", 2), "Petróleo (Brent)": ("BZ=F", 2), "Bitcoin": ("BTC-USD", 2), "Ethereum": ("ETH-USD", 2), "Solana": ("SOL-USD", 2), "Ibovespa": ("^BVSP", 2), "S&P 500": ("^GSPC", 2), "Dow Jones": ("^DJI", 2), "Nasdaq": ("^IXIC", 2), "DAX (Alem)": ("^GDAXI", 2), "Nikkei (Jap)": ("^N225", 2), "Shanghai (Chi)": ("000001.SS", 2), "Shenzhen (Chi)": ("399001.SZ", 2), "Merval (Arg)": ("^MERV", 2)}
acoes_br_list = ["AGRO3.SA", "AMOB3.SA", "BBAS3.SA", "BBDC3.SA", "BBSE3.SA", "BRSR6.SA", "B3SA3.SA", "CMIG3.SA", "CXSE3.SA", "EGIE3.SA", "EQTL3.SA", "EZTC3.SA", "FLRY3.SA", "GMAT3.SA", "ITSA4.SA", "KEPL3.SA", "KLBN3.SA", "LEVE3.SA", "PETR3.SA", "PRIO3.SA", "PSSA3.SA", "RAIZ4.SA", "RANI3.SA", "SAPR4.SA", "SBFG3.SA", "SMTO3.SA", "SOJA3.SA", "SUZB3.SA", "TAEE11.SA", "TTEN3.SA", "VAMO3.SA", "VIVT3.SA", "WEGE3.SA", "ETHE11.SA", "GOLD11.SA", "QSOL11.SA", "QBTC11.SA"]
acoes_br_dict = {ticker.replace(".SA", ""): (ticker, 2) for ticker in acoes_br_list}
acoes_usa_list = ["GOOGL", "AMZN", "NVDA", "TSM", "ASML", "AVGO", "IRS", "TSLA", "MU", "VZ", "T", "HD", "SHOP", "DIS", "SPG", "ANET", "ICE", "KO", "EQNR", "EPR", "WFC", "VICI", "O", "CPRT", "ASX", "CEPU", "NVO", "PLTR", "JBL", "QCOM", "AAPL", "MSFT", "BAC", "ORCL", "EQT", "MNST", "CVS", "HUYA", "GPC", "PFE", "ROKU", "DIBS", "LEG", "MBUU", "FVRR"]
acoes_usa_dict = {ticker: (ticker, 2) for ticker in acoes_usa_list}

# --- CRIAÇÃO DAS ABAS ---
aba_macro, aba_br, aba_usa, aba_fundamentos, aba_valuation, aba_analises, aba_simulador = st.tabs([
    "🌍 Visão Macro", "🇧🇷 Ações Brasil", "🇺🇸 Ações EUA", "📊 Fundamentos", "🧮 Valuation Pro", "🎯 Raio-X & IA", "🎛️ Simulador"
])

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

# --- CARREGAMENTO E MESCLAGEM DOS DADOS (O MOTOR HÍBRIDO) ---
arquivo_csv = "base_dados.csv"
arquivo_cofre = "cofre_consenso.csv"
dados_base_carregados = False

if os.path.exists(arquivo_csv):
    df = pd.read_csv(arquivo_csv, sep=";")
    dados_base_carregados = True
    
    # Cálculos Clássicos dos Gurus
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
    df['Saude_Visual'] = df['F_Score'].apply(lambda x: "⭐" * int(x) if pd.notnull(x) and x > 0 else "Sem Nota")

    mask_magica = (df['EV_EBIT'] > 0) & (df['ROIC_%'] > 0)
    df.loc[mask_magica, 'Rank_ROIC'] = df.loc[mask_magica, 'ROIC_%'].rank(ascending=False)
    df.loc[mask_magica, 'Rank_EV_EBIT'] = df.loc[mask_magica, 'EV_EBIT'].rank(ascending=True)
    df.loc[mask_magica, 'Pontuacao_Magica'] = df['Rank_ROIC'] + df['Rank_EV_EBIT']

    # --- LENDO O COFRE DO ROBÔ ---
    if os.path.exists(arquivo_cofre):
        df_cofre = pd.read_csv(arquivo_cofre, sep=";")
        # Remove duplicatas por segurança e mescla com a base principal
        df_cofre = df_cofre.drop_duplicates(subset=['Ticker'], keep='last')
        df = pd.merge(df, df_cofre[['Ticker', 'Val_Pessimista', 'Val_Base', 'Val_Otimista', 'Num_Analistas', 'Recomendacao']], on='Ticker', how='left')
    
    # Garante que as colunas existam mesmo se o cofre não existir
    for col in ['Val_Pessimista', 'Val_Base', 'Val_Otimista', 'Num_Analistas']:
        if col not in df.columns: df[col] = 0
        df[col] = df[col].fillna(0)
    if 'Recomendacao' not in df.columns: df['Recomendacao'] = 'N/A'

    # --- O PLANO B: DCF MATEMÁTICO DO TERMINAL ---
    # Parâmetros Macro para o cálculo do DCF
    df['Taxa_Apli'] = np.where(df['Origem'].str.contains("BRAPI|Fundamentus"), taxa_selic_live, taxa_us10y_live)
    df['Ke'] = (df['Taxa_Apli'] / 100) + 0.055 # Prêmio de risco padrão 5.5%
    df['g_base'] = df['Crescimento_5a_%'].fillna(0).clip(lower=0, upper=10) / 100
    df['g_otimista'] = df['Crescimento_5a_%'].fillna(0).clip(lower=0, upper=15) / 100

    def calcular_dcf_realista(lpa, preco_atual, ke_ajustado, g_curto_prazo, g_perpetuidade):
        if lpa <= 0 or pd.isna(lpa): return 0
        
        pv_estagio1 = 0
        lucro_temp = lpa
        for i in range(1, 6):
            lucro_temp *= (1 + g_curto_prazo)
            pv_estagio1 += lucro_temp / ((1 + ke_ajustado) ** i)
            
        if ke_ajustado <= g_perpetuidade: return 0 
            
        valor_terminal = (lucro_temp * (1 + g_perpetuidade)) / (ke_ajustado - g_perpetuidade)
        pv_terminal = valor_terminal / ((1 + ke_ajustado) ** 5)
        
        valor_intrinseco = pv_estagio1 + pv_terminal
        
        # O Sanity Check (Atenuador Proporcional)
        if preco_atual > 0 and valor_intrinseco > preco_atual * 1.5:
            teto_livre = preco_atual * 1.5
            excesso = valor_intrinseco - teto_livre
            valor_intrinseco = teto_livre + (excesso * 0.15)
            
        return valor_intrinseco

    # --- A MESCLAGEM HÍBRIDA FINAL ---
    v_pess_final, v_base_final, v_otim_final, metodo_final = [], [], [], []
    
    for index, row in df.iterrows():
        # Se o Cofre tem o Consenso, usa ele
        if row['Val_Base'] > 0:
            v_pess_final.append(row['Val_Pessimista'])
            v_base_final.append(row['Val_Base'])
            v_otim_final.append(row['Val_Otimista'])
            metodo_final.append("Consenso Analistas")
        # Se o Cofre veio vazio, o Terminal calcula na hora
        else:
            pess = calcular_dcf_realista(row['LPA'], row['Preco'], row['Ke'] + 0.02, 0.0, 0.01)
            base = calcular_dcf_realista(row['LPA'], row['Preco'], row['Ke'], row['g_base'], 0.03)
            otim = calcular_dcf_realista(row['LPA'], row['Preco'], max(row['Ke'] - 0.01, 0.07), row['g_otimista'], 0.035)
            v_pess_final.append(pess)
            v_base_final.append(base)
            v_otim_final.append(otim)
            metodo_final.append("DCF Matemático (Terminal)")

    # Aplica as listas finais de volta ao dataframe
    df['Val_Pessimista'] = v_pess_final
    df['Val_Base'] = v_base_final
    df['Val_Otimista'] = v_otim_final
    df['Metodo_Valuation'] = metodo_final
    df['Justo_Mercado'] = df['Val_Base'] # Alvo principal para o Simulador

    # --- ABA DE VALUATION PRO (HÍBRIDA) ---
    with aba_valuation:
        st.header("🧮 Valuation Institucional (Painel Híbrido)")
        st.write("Agregação do Consenso de Mercado. Se o ativo não tiver cobertura de analistas, o terminal aciona o algoritmo DCF de 2 estágios.")
        
        df_cenarios = df.copy()
        df_cenarios = df_cenarios[['Ticker', 'Preco', 'Val_Pessimista', 'Val_Base', 'Val_Otimista', 'Num_Analistas', 'Recomendacao', 'Metodo_Valuation', 'Origem']]
        df_cenarios = df_cenarios[df_cenarios['Val_Base'] > 0]
        
        df_cenarios['Margem_Base'] = ((df_cenarios['Val_Base'] - df_cenarios['Preco']) / df_cenarios['Preco']) * 100
        df_cenarios = df_cenarios.sort_values(by='Margem_Base', ascending=False)
        
        def formata_val(linha, col):
            simb = "R$" if "Fundamentus" in str(linha['Origem']) else "$"
            return f"{simb} {linha[col]:.2f}"
            
        df_cenarios['Preco Atual'] = df_cenarios.apply(lambda r: formata_val(r, 'Preco'), axis=1)
        df_cenarios['🔴 Alvo Pessimista'] = df_cenarios.apply(lambda r: formata_val(r, 'Val_Pessimista'), axis=1)
        df_cenarios['🟡 Alvo Base (Média/Justo)'] = df_cenarios.apply(lambda r: formata_val(r, 'Val_Base'), axis=1)
        df_cenarios['🟢 Alvo Otimista'] = df_cenarios.apply(lambda r: formata_val(r, 'Val_Otimista'), axis=1)
        
        st.dataframe(
            df_cenarios[['Ticker', 'Preco Atual', '🔴 Alvo Pessimista', '🟡 Alvo Base (Média/Justo)', '🟢 Alvo Otimista', 'Num_Analistas', 'Recomendacao', 'Metodo_Valuation']], 
            use_container_width=True, hide_index=True
        )

    # --- ABA DE FUNDAMENTOS ---
    with aba_fundamentos:
        st.header("Radar de Valor e Qualidade (Gurus Clássicos)")
        df_fundo = df.copy()
        
        mercado = st.radio("Mercado Alvo:", ["Todos", "Ações Brasil", "Ações EUA"], horizontal=True)
        if mercado == "Ações Brasil": df_fundo = df_fundo[df_fundo['Origem'].str.contains("BRAPI|Fundamentus", na=False)]
        elif mercado == "Ações EUA": df_fundo = df_fundo[df_fundo['Origem'].str.contains("Finnhub|Yahoo", na=False)]
        
        df_fundo = df_fundo.sort_values(by='F_Score', ascending=False)
        
        colunas_dinheiro = ['Preco', 'Teto_Bazin', 'Justo_Graham', 'Justo_Mercado']
        def formatar_moeda(linha, nome_coluna):
            valor = linha[nome_coluna]
            if pd.isna(valor) or valor == 0: return "N/A"
            simbolo = "R$" if "Fundamentus" in str(linha['Origem']) else "$"
            return f"{simbolo} {valor:.2f}"

        for col in colunas_dinheiro:
            df_fundo[col] = df_fundo.apply(lambda row: formatar_moeda(row, col), axis=1)
            
        st.dataframe(df_fundo[['Ticker', 'Preco', 'Saude_Visual', 'ROIC_%', 'Teto_Bazin', 'Justo_Graham']], use_container_width=True, hide_index=True)

    # --- ABA SIMULADOR PONDERADO ---
    with aba_simulador:
        st.header("🎛️ Laboratório de Estratégia Ponderada")
        
        with st.expander("Defina seus Pesos de Decisão (0 a 100%)", expanded=True):
            c1, c2, c3, c4, c5 = st.columns(5)
            w_graham = c1.slider("Valor (Graham)", 0, 100, 20)
            w_bazin = c2.slider("Renda (Bazin)", 0, 100, 20)
            w_magic = c3.slider("Qualidade (Magic)", 0, 100, 20)
            w_fscore = c4.slider("Saúde (F-Score)", 0, 100, 20)
            w_dcf = c5.slider("Mercado (Consenso/DCF)", 0, 100, 20)

        df_sim = df.copy()
        df_sim['Margem_Mercado_%'] = np.where(df_sim['Val_Base'] > 0, ((df_sim['Val_Base'] - df_sim['Preco']) / df_sim['Preco']) * 100, 0)
        df_sim['N_Graham'] = df_sim['Margem_Graham_%'].rank(pct=True) * 100
        df_sim['N_Bazin'] = df_sim['Margem_Bazin_%'].rank(pct=True) * 100
        df_sim['N_Mercado'] = df_sim['Margem_Mercado_%'].rank(pct=True) * 100
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

        def fmt_sim_moeda(linha):
            simb = "R$" if "Fundamentus" in str(linha['Origem']) else "$"
            return f"{simb} {linha['Preco']:.2f}"
        
        df_sim['Preco_Atual'] = df_sim.apply(fmt_sim_moeda, axis=1)
        st.dataframe(df_sim[['Rank', 'Ticker', 'Preco_Atual', 'Nota_Final', 'Veredito', 'Saude_Visual']], use_container_width=True, hide_index=True)

else: 
    with aba_valuation: st.warning("⚠️ Execute o 'robo_balancos.py' primeiro.")
    with aba_fundamentos: st.warning("⚠️ Execute o 'robo_balancos.py' primeiro.")
    with aba_simulador: st.warning("⚠️ Execute o 'robo_balancos.py' primeiro.")

# --- ABA DE ANÁLISES (TÉCNICA + IA NO RAG DE CONSENSO) ---
with aba_analises:
    st.header("🎯 Central de Inteligência Profissional")
    st.write("Selecione um ativo para realizar análises cruzadas sob demanda.")
    
    col1, col2, col3 = st.columns([2, 1, 1])
    todos_ativos = [t for t in acoes_br_list + acoes_usa_list if "11.SA" not in t]
    ativo_selecionado = col1.selectbox("Escolha a Ação:", sorted(todos_ativos))
    
    if col2.button("📈 Abrir Raio-X Técnico (Gráficos)", use_container_width=True):
        abrir_raio_x(ativo_selecionado)
        
    if col3.button("🧠 Gerar Veredito IA", use_container_width=True):
        dados_envio = None
        if dados_base_carregados:
            ticker_limpo = ativo_selecionado.replace(".SA", "")
            linha = df[df['Ticker'].str.contains(ticker_limpo, na=False)]
            if not linha.empty:
                dados_envio = linha.iloc[0].to_dict()
        
        gerar_relatorio_ia(ativo_selecionado, dados_envio)
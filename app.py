import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
import requests
from datetime import datetime
import os
import json
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

# --- ESTILO CSS GLOBAL PARA TABELAS ---
ESTILO_TABELA_PRO = """
<style>
.tabela-pro { width: 100%; border-collapse: collapse; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #1e1e1e; border-radius: 8px; overflow: hidden; margin-bottom: 20px;}
.tabela-pro th { background-color: #151515; color: #ff9900; font-size: 11px; text-transform: uppercase; padding: 14px 12px; text-align: left; border-bottom: 2px solid #333; }
.tabela-pro td { padding: 14px 12px; border-bottom: 1px solid #2b2b2b; color: #ecf0f1; font-size: 13px; font-weight: bold; }
.tabela-pro tr:hover { background-color: #252525; }
.tabela-ativo { color: #3498db !important; font-weight: bold; text-decoration: none; }
</style>
"""

# --- MOTOR DE COTAÇÕES EM LOTE ---
@st.cache_data(ttl=300)
def buscar_dados_em_lote(lista_tickers, mercado="Macro"):
    try:
        dados = yf.download(" ".join(lista_tickers), period="14d", interval="1d", progress=False)
        fechamentos = pd.DataFrame(dados['Close']) if isinstance(dados['Close'], pd.Series) else dados['Close']
        if len(lista_tickers) == 1: fechamentos.columns = lista_tickers
        
        fonte_str = "Yahoo Finance"
        
        if mercado == "BR" and BRAPI_KEY:
            try:
                tickers_limpos = [t.replace(".SA", "") for t in lista_tickers]
                url = f"https://brapi.dev/api/quote/{','.join(tickers_limpos)}?token={BRAPI_KEY}"
                res = requests.get(url, timeout=5).json()
                if 'results' in res:
                    for item in res['results']:
                        t_yf = item['symbol'] + ".SA"
                        preco_live = item.get('regularMarketPrice')
                        if t_yf in fechamentos.columns and preco_live is not None:
                            fechamentos.loc[fechamentos.index[-1], t_yf] = preco_live
                    fonte_str = "BRAPI + YF"
            except: pass
            
        return fechamentos.tail(10), fonte_str
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

# --- DIALOGO: DASHBOARD DE VEREDITO (ESTILO INSTITUCIONAL EM JSON) ---
@st.dialog("🧠 Painel de Inteligência e Veredito IA", width="large")
def gerar_relatorio_ia_dashboard(ticker, dados_fundos=None):
    if not GOOGLE_API_KEY: return st.error("⚠️ Configure sua GOOGLE_API_KEY para gerar a análise.")
    st.markdown(f"<h3 style='text-align: center; color: #ecf0f1; font-family: sans-serif;'>{ticker}</h3>", unsafe_allow_html=True)
    
    with st.spinner("Processando gráfico, coletando notícias e acionando IA..."):
        try:
            # 1. GRÁFICO DE ÁREA DO TOPO
            moeda_ia = "R$" if ".SA" in ticker else "US$"
            ativo_yf = yf.Ticker(ticker)
            dados_hist = ativo_yf.history(period="1y")
            
            preco_atual_ia, suporte_ia, resistencia_ia = "N/A", "N/A", "N/A"
            tendencia_cp = "Neutra"
            
            if not dados_hist.empty:
                df_tec_ia = calcular_indicadores_tecnicos(dados_hist)
                sup_ia, res_ia = encontrar_suportes_resistencias(df_tec_ia)
                preco_atual_num = df_tec_ia['Close'].iloc[-1]
                preco_atual_ia = f"{moeda_ia} {preco_atual_num:.2f}"
                if sup_ia: suporte_ia = f"{moeda_ia} {sup_ia[0]:.2f}"
                if res_ia: resistencia_ia = f"{moeda_ia} {res_ia[0]:.2f}"
                
                preco_inicio = df_tec_ia['Close'].iloc[0]
                if preco_atual_num >= preco_inicio:
                    cor_grafico = '#00cc66'
                    fill_grafico = 'rgba(0, 204, 102, 0.2)'
                    tendencia_cp = "Alta" if df_tec_ia['SMA_20'].iloc[-1] > df_tec_ia['SMA_20'].iloc[-20] else "Baixa"
                else:
                    cor_grafico = '#ff4b4b'
                    fill_grafico = 'rgba(255, 75, 75, 0.2)'
                    tendencia_cp = "Baixa"
                
                fig_top = go.Figure(go.Scatter(x=df_tec_ia.index, y=df_tec_ia['Close'], mode='lines', line=dict(color=cor_grafico, width=2), fill='tozeroy', fillcolor=fill_grafico))
                fig_top.update_layout(template="plotly_dark", height=200, margin=dict(l=0, r=0, t=0, b=0), xaxis_visible=False, yaxis_visible=True, showlegend=False, plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig_top, use_container_width=True, config={'displayModeBar': False})

            # 2. COLETA DE NOTÍCIAS E DADOS DA IA
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
            except: pass

            if len(noticias_validas) > 5:
                texto_noticias = "".join(noticias_validas[:40])
            else:
                termo_busca = ticker.replace(".SA", "")
                params = "hl=en-US&gl=US&ceid=US:en" if is_usa else "hl=pt-BR&gl=BR&ceid=BR:pt-419"
                url_news = f"https://news.google.com/rss/search?q={termo_busca}+stock+market&{params}" if is_usa else f"https://news.google.com/rss/search?q={termo_busca}+ação+mercado&{params}"
                try:
                    resp = requests.get(url_news, timeout=10)
                    if resp.status_code == 200:
                        root = ET.fromstring(resp.text)
                        for item in root.findall('.//item')[:40]:
                            t = item.find('title').text if item.find('title') is not None else ""
                            d = item.find('pubDate').text[5:16] if item.find('pubDate') is not None else "Recente"
                            f = item.find('source').text if item.find('source') is not None else "Portal Financeiro"
                            if t: texto_noticias += f"- Data: {d} | Fonte: {f} | Título: {t}\n"
                except: pass
                    
            if not texto_noticias.strip(): texto_noticias = "Sem notícias recentes mapeadas nas fontes globais e locais."

            v_pessimista = dados_fundos.get('Val_Pessimista', 0) if dados_fundos else 0
            v_base = dados_fundos.get('Val_Base', 0) if dados_fundos else 0
            v_otimista = dados_fundos.get('Val_Otimista', 0) if dados_fundos else 0
            
            contexto_dados = f"""
            Preço Atual: {preco_atual_ia}
            Suporte: {suporte_ia} | Resistência: {resistencia_ia}
            Alvo Pessimista: {moeda_ia} {v_pessimista:.2f}
            Alvo Base: {moeda_ia} {v_base:.2f}
            Alvo Otimista: {moeda_ia} {v_otimista:.2f}
            """

            # 3. PROMPT JSON PARA A IA
            prompt = f"""
            Atue como Analista Chefe. Analise {ticker} com base nestes dados:
            {contexto_dados}
            MANCHETES: {texto_noticias}
            
            Você DEVE retornar APENAS um objeto JSON válido (sem marcações markdown como ```json), com a exata estrutura abaixo:
            {{
              "diagnostico_grafico_texto": "1 frase resumindo a tendência de preço frente ao suporte e resistência.",
              "analise_tendencia_fundamental": "1 parágrafo robusto avaliando a saúde operacional (lucro, dívida, macroeconomia) e justificando o momento da empresa.",
              "swot": {{
                "S": ["Força 1", "Força 2", "Força 3"],
                "W": ["Fraqueza 1", "Fraqueza 2", "Fraqueza 3"],
                "O": ["Oportunidade 1", "Oportunidade 2", "Oportunidade 3"],
                "T": ["Ameaça 1", "Ameaça 2", "Ameaça 3"]
              }},
              "tese_pessimista": "1 parágrafo justificando por que a ação pode cair para o alvo pessimista.",
              "tese_base": "1 parágrafo justificando o preço alvo base.",
              "tese_otimista": "1 parágrafo justificando o potencial de alta para o alvo otimista.",
              "noticias_positivas": [
                {{"fonte": "Nome", "manchete": "Título", "resumo": "1 linha de explicação"}}
              ],
              "noticias_negativas": [
                {{"fonte": "Nome", "manchete": "Título", "resumo": "1 linha de explicação"}}
              ]
            }}
            """
            
            model = genai.GenerativeModel('gemini-2.5-flash-lite')
            response = model.generate_content(prompt)
            
            raw_json = response.text.replace("```json", "").replace("```", "").strip()
            ia_data = json.loads(raw_json)

            # 4. PREPARAÇÃO DOS DADOS DO DASHBOARD
            dy = f"{dados_fundos.get('Div_Yield_%', 0):.2f}%" if dados_fundos and pd.notnull(dados_fundos.get('Div_Yield_%')) else "-"
            pl = f"{dados_fundos.get('Preco', 0) / dados_fundos.get('LPA', 1):.2f}" if dados_fundos and dados_fundos.get('LPA', 0) > 0 else "-"
            peg = "-"
            pvp = f"{dados_fundos.get('Preco', 0) / dados_fundos.get('VPA', 1):.2f}" if dados_fundos and dados_fundos.get('VPA', 0) > 0 else "-"
            evebit = f"{dados_fundos.get('EV_EBIT', 0):.2f}" if dados_fundos and dados_fundos.get('EV_EBIT', 0) > 0 else "-"
            vpa = f"{dados_fundos.get('VPA', 0):.2f}" if dados_fundos and pd.notnull(dados_fundos.get('VPA')) else "-"
            
            liq_corr = f"{dados_fundos.get('Liquidez_Corrente', 0):.2f}" if dados_fundos and pd.notnull(dados_fundos.get('Liquidez_Corrente')) else "-"
            margem_liq = f"{dados_fundos.get('Margem_Liquida_%', 0):.2f}%" if dados_fundos and pd.notnull(dados_fundos.get('Margem_Liquida_%')) else "-"
            roe = f"{dados_fundos.get('ROE_%', 0):.2f}%" if dados_fundos and pd.notnull(dados_fundos.get('ROE_%')) else "-"
            div_liq_pl = "-"

            def render_estrelas(condicao):
                return "★★★★★" if condicao else "★★☆☆☆"

            star_roe = render_estrelas(dados_fundos.get('ROE_%', 0) > 10) if dados_fundos else "---"
            star_roic = render_estrelas(dados_fundos.get('ROIC_%', 0) > 10) if dados_fundos else "---"
            star_margem = render_estrelas(dados_fundos.get('Margem_Liquida_%', 0) > 5) if dados_fundos else "---"
            star_divida = render_estrelas(dados_fundos.get('Liquidez_Corrente', 0) > 1.2) if dados_fundos else "---"
            star_cresc = render_estrelas(dados_fundos.get('Crescimento_5a_%', 0) > 5) if dados_fundos else "---"

            html_noticias_positivas = ""
            for n in ia_data.get('noticias_positivas', []):
                html_noticias_positivas += f"<li class='news-item' style='border-left-color:#27ae60;'><span class='news-meta'>{n.get('fonte', '')}</span><span class='news-title'>{n.get('manchete', '')}</span><span style='color:#bdc3c7;'>{n.get('resumo', '')}</span></li>"

            html_noticias_negativas = ""
            for n in ia_data.get('noticias_negativas', []):
                html_noticias_negativas += f"<li class='news-item' style='border-left-color:#c0392b;'><span class='news-meta'>{n.get('fonte', '')}</span><span class='news-title'>{n.get('manchete', '')}</span><span style='color:#bdc3c7;'>{n.get('resumo', '')}</span></li>"

            swot_s = '<br>• '.join([''] + ia_data.get('swot', {}).get('S', []))
            swot_w = '<br>• '.join([''] + ia_data.get('swot', {}).get('W', []))
            swot_o = '<br>• '.join([''] + ia_data.get('swot', {}).get('O', []))
            swot_t = '<br>• '.join([''] + ia_data.get('swot', {}).get('T', []))

            # IMPORTANTE: REMOVIDA A INDENTAÇÃO PARA O STREAMLIT NÃO LER COMO MARKDOWN CODE BLOCK
            dashboard_html = f"""
<style>
.dash-bg {{ background-color: #121212; color: #ecf0f1; font-family: 'Segoe UI', Arial, sans-serif; padding: 15px; border-radius: 8px; font-size: 13px; }}
.aviso-badge {{ background-color: #1a252f; border: 1px solid #3498db; color: #3498db; text-align: center; padding: 8px; border-radius: 4px; font-weight: bold; margin-bottom: 15px; }}
.section-title {{ color: #d35400; font-size: 11px; font-weight: bold; border-bottom: 1px dashed #333; margin-top: 20px; padding-bottom: 5px; text-transform: uppercase; margin-bottom: 10px; display: flex; align-items: center; gap: 5px; }}
.metric-grid-3 {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 10px; }}
.metric-box-dark {{ border: 1px solid #333; padding: 10px; text-align: center; border-radius: 4px; background: #1a1a1a; }}
.metric-title {{ color: #7f8c8d; font-size: 10px; text-transform: uppercase; display: block; margin-bottom: 5px; }}
.metric-val-green {{ color: #27ae60; font-weight: bold; font-size: 16px; }}
.metric-val-red {{ color: #c0392b; font-weight: bold; font-size: 16px; }}
.kpi-grid-6 {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px; margin-bottom: 5px; }}
.kpi-grid-4 {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 5px; }}
.kpi-item .label {{ color: #7f8c8d; font-size: 9px; text-transform: uppercase; }}
.kpi-item .val {{ color: #ecf0f1; font-weight: bold; font-size: 14px; display: block; margin-top: 2px; }}
.text-box {{ color: #bdc3c7; font-size: 12px; line-height: 1.5; text-align: justify; }}
.swot-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px; }}
.swot-card {{ padding: 12px; border-radius: 4px; background: #1a1a1a; font-size: 11px; color: #bdc3c7; }}
.swot-s {{ border: 1px solid #27ae60; }} .swot-w {{ border: 1px solid #c0392b; }}
.swot-o {{ border: 1px solid #2980b9; }} .swot-t {{ border: 1px solid #f39c12; }}
.swot-title {{ font-weight: bold; margin-bottom: 5px; display: block; }}
.placar-row {{ display: flex; justify-content: space-between; border-bottom: 1px solid #222; padding: 6px 0; font-size: 12px; color: #bdc3c7; }}
.stars {{ color: #f1c40f; letter-spacing: 2px; }}
.val-bar-container {{ display: flex; height: 6px; width: 100%; border-radius: 3px; overflow: hidden; margin: 15px 0; }}
.val-bar-red {{ background-color: #c0392b; flex: 1; }}
.val-bar-yellow {{ background-color: #f39c12; flex: 1; }}
.val-bar-green {{ background-color: #27ae60; flex: 1; }}
.val-labels {{ display: flex; justify-content: space-between; font-weight: bold; font-size: 14px; margin-bottom: 15px; }}
.val-pess {{ color: #c0392b; }} .val-base {{ color: #f39c12; text-align: center; }} .val-otim {{ color: #27ae60; text-align: right; }}
.tese-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }}
.tese-card {{ border: 1px solid #333; padding: 10px; border-radius: 4px; font-size: 11px; color: #bdc3c7; line-height: 1.4; text-align: justify; }}
.news-list {{ list-style-type: none; padding: 0; margin: 0; }}
.news-item {{ margin-bottom: 10px; font-size: 12px; border-left: 2px solid #555; padding-left: 10px; }}
.news-title {{ font-weight: bold; color: #ecf0f1; display: block; }}
.news-meta {{ color: #7f8c8d; font-size: 10px; margin-bottom: 2px; display: block; }}
</style>
<div class="dash-bg">
<div class="aviso-badge">🛡️ Análise Assistida por IA — Baseada em Consenso e Indicadores Técnicos</div>
<div class="section-title">🔒 DIAGNÓSTICO GRÁFICO (IA)</div>
<div class="metric-grid-3">
<div class="metric-box-dark"><span class="metric-title">Tendência Curto Prazo</span><span class="{'metric-val-green' if tendencia_cp == 'Alta' else 'metric-val-red'}">{tendencia_cp}</span></div>
<div class="metric-box-dark"><span class="metric-title">Zona de Suporte</span><span class="metric-val-green">{suporte_ia}</span></div>
<div class="metric-box-dark"><span class="metric-title">Zona de Resistência</span><span class="metric-val-red">{resistencia_ia}</span></div>
</div>
<div class="text-box" style="text-align: center; font-style: italic;">"{ia_data.get('diagnostico_grafico_texto', '')}"</div>
<div class="section-title">📊 INDICADORES DE VALUATION</div>
<div class="kpi-grid-6">
<div class="kpi-item"><span class="label">D.Y</span><span class="val">{dy}</span></div>
<div class="kpi-item"><span class="label">P/L</span><span class="val">{pl}</span></div>
<div class="kpi-item"><span class="label">PEG RATIO</span><span class="val">{peg}</span></div>
<div class="kpi-item"><span class="label">P/VP</span><span class="val">{pvp}</span></div>
<div class="kpi-item"><span class="label">EV/EBITDA</span><span class="val">{evebit}</span></div>
<div class="kpi-item"><span class="label">VPA</span><span class="val">{vpa}</span></div>
</div>
<div class="section-title">⚖️ INDICADORES DE ENDIVIDAMENTO & RENTABILIDADE</div>
<div class="kpi-grid-4">
<div class="kpi-item"><span class="label">Dív. Líquida / PL</span><span class="val">{div_liq_pl}</span></div>
<div class="kpi-item"><span class="label">Liq. Corrente</span><span class="val">{liq_corr}</span></div>
<div class="kpi-item"><span class="label">Margem Líquida</span><span class="val">{margem_liq}</span></div>
<div class="kpi-item"><span class="label">ROE</span><span class="val">{roe}</span></div>
</div>
<div class="section-title">🧠 DIAGNÓSTICO SÊNIOR & INTELIGÊNCIA SETORIAL</div>
<div class="text-box">{ia_data.get('analise_tendencia_fundamental', '')}</div>
<div class="section-title">🎯 MATRIZ SWOT SETORIAL</div>
<div class="swot-grid">
<div class="swot-card swot-s"><span class="swot-title" style="color:#27ae60;">S - Forças</span>{swot_s}</div>
<div class="swot-card swot-w"><span class="swot-title" style="color:#c0392b;">W - Fraquezas</span>{swot_w}</div>
<div class="swot-card swot-o"><span class="swot-title" style="color:#2980b9;">O - Oportunidades</span>{swot_o}</div>
<div class="swot-card swot-t"><span class="swot-title" style="color:#f39c12;">T - Ameaças</span>{swot_t}</div>
</div>
<div class="section-title">🏆 PLACAR FUNDAMENTALISTA VS SETOR</div>
<div class="placar-row"><span>ROE (Retorno do Acionista)</span><span class="stars">{star_roe}</span></div>
<div class="placar-row"><span>ROIC (Retorno s/ Capital)</span><span class="stars">{star_roic}</span></div>
<div class="placar-row"><span>Margem Líquida</span><span class="stars">{star_margem}</span></div>
<div class="placar-row"><span>Saúde da Dívida</span><span class="stars">{star_divida}</span></div>
<div class="placar-row" style="border:none;"><span>Cresc. Receita Líquida</span><span class="stars">{star_cresc}</span></div>
<div class="section-title">📰 TERMÔMETRO DE NOTÍCIAS (TOP 10)</div>
<div class="swot-grid" style="align-items: start;">
<div>
<span style="color:#27ae60; font-weight:bold; font-size:12px; margin-bottom:10px; display:block;">🟢 Otimismo do Mercado</span>
<ul class="news-list">
{html_noticias_positivas}
</ul>
</div>
<div>
<span style="color:#c0392b; font-weight:bold; font-size:12px; margin-bottom:10px; display:block;">🔴 Alertas e Riscos</span>
<ul class="news-list">
{html_noticias_negativas}
</ul>
</div>
</div>
<div class="section-title">🔮 VALUATION CONSENSO & PROJEÇÕES</div>
<div class="val-bar-container">
<div class="val-bar-red"></div><div class="val-bar-yellow"></div><div class="val-bar-green"></div>
</div>
<div class="val-labels">
<div class="val-pess">{moeda_ia} {v_pessimista:.2f}<br><span style="font-size:9px; color:#7f8c8d;">PESSIMISTA</span></div>
<div class="val-base">{moeda_ia} {v_base:.2f}<br><span style="font-size:9px; color:#7f8c8d;">ALVO BASE</span></div>
<div class="val-otim">{moeda_ia} {v_otimista:.2f}<br><span style="font-size:9px; color:#7f8c8d;">OTIMISTA</span></div>
</div>
<div class="tese-grid">
<div class="tese-card" style="border-color: #c0392b;"><span style="color:#c0392b; font-weight:bold; display:block; margin-bottom:5px;">Tese Pessimista</span>{ia_data.get('tese_pessimista', '')}</div>
<div class="tese-card" style="border-color: #f39c12;"><span style="color:#f39c12; font-weight:bold; display:block; margin-bottom:5px;">Tese Base</span>{ia_data.get('tese_base', '')}</div>
<div class="tese-card" style="border-color: #27ae60;"><span style="color:#27ae60; font-weight:bold; display:block; margin-bottom:5px;">Tese Otimista</span>{ia_data.get('tese_otimista', '')}</div>
</div>
</div>
"""
            st.markdown(dashboard_html, unsafe_allow_html=True)
            
        except Exception as e:
            st.error(f"Erro ao processar dashboard: {e}")

# --- LISTAS DE ATIVOS ---
macro_dict = {"Dólar": ("USDBRL=X", 3), "Euro": ("EURBRL=X", 3), "Ouro": ("GC=F", 2), "Petróleo (Brent)": ("BZ=F", 2), "Bitcoin": ("BTC-USD", 2), "Ethereum": ("ETH-USD", 2), "Solana": ("SOL-USD", 2), "Ibovespa": ("^BVSP", 2), "S&P 500": ("^GSPC", 2), "Dow Jones": ("^DJI", 2), "Nasdaq": ("^IXIC", 2), "DAX (Alem)": ("^GDAXI", 2), "Nikkei (Jap)": ("^N225", 2), "Shanghai (Chi)": ("000001.SS", 2), "Shenzhen (Chi)": ("399001.SZ", 2), "Merval (Arg)": ("^MERV", 2)}

acoes_br_list = ["AGRO3.SA", "AMOB3.SA", "BBAS3.SA", "BBDC3.SA", "BBSE3.SA", "BRSR6.SA", "B3SA3.SA", "CMIG3.SA", "CXSE3.SA", "EGIE3.SA", "EQTL3.SA", "EZTC3.SA", "FLRY3.SA", "GMAT3.SA", "ITSA4.SA", "KEPL3.SA", "KLBN3.SA", "LEVE3.SA", "PETR3.SA", "PRIO3.SA", "PSSA3.SA", "RAIZ4.SA", "RANI3.SA", "SAPR4.SA", "SBFG3.SA", "SMTO3.SA", "SOJA3.SA", "SUZB3.SA", "TAEE11.SA", "TTEN3.SA", "VAMO3.SA", "VIVT3.SA", "WEGE3.SA", "ETHE11.SA", "GOLD11.SA", "QSOL11.SA", "QBTC11.SA"]
acoes_br_dict = {ticker.replace(".SA", ""): (ticker, 2) for ticker in acoes_br_list}

acoes_usa_list = ["GOOGL", "AMZN", "NVDA", "TSM", "ASML", "AVGO", "IRS", "TSLA", "MU", "VZ", "T", "HD", "SHOP", "DIS", "SPG", "ANET", "ICE", "KO", "EQNR", "EPR", "WFC", "VICI", "O", "CPRT", "ASX", "CEPU", "NVO", "PLTR", "JBL", "QCOM", "AAPL", "MSFT", "BAC", "ORCL", "EQT", "MNST", "CVS", "HUYA", "GPC", "PFE", "ROKU", "DIBS", "LEG", "MBUU", "FVRR"]
acoes_usa_dict = {ticker: (ticker, 2) for ticker in acoes_usa_list}

# --- FUNÇÕES GERADORAS DE BADGES ---
def gerar_badge_recomendacao(rec):
    rec_str = str(rec).strip().lower()
    if rec_str in ['nan', 'none', 'n/a', '']:
        return "<span style='color: #7f8c8d; font-weight: bold;'>---</span>"
    
    if "strong buy" in rec_str:
        cor, bg, texto = "#00b894", "rgba(0, 184, 148, 0.1)", "Strong Buy"
    elif "buy" in rec_str:
        cor, bg, texto = "#00cc66", "rgba(0, 204, 102, 0.1)", "Buy"
    elif "hold" in rec_str:
        cor, bg, texto = "#f1c40f", "rgba(241, 196, 15, 0.1)", "Hold"
    elif "strong sell" in rec_str:
        cor, bg, texto = "#c0392b", "rgba(192, 57, 43, 0.1)", "Strong Sell"
    elif "sell" in rec_str:
        cor, bg, texto = "#ff4b4b", "rgba(255, 75, 75, 0.1)", "Sell"
    else:
        cor, bg, texto = "#bdc3c7", "rgba(189, 195, 199, 0.1)", str(rec).title()
        
    estilo = f"border: 1px solid {cor}; color: {cor}; padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: bold; background-color: {bg}; text-transform: uppercase;"
    return f"<span style='{estilo}'>{texto}</span>"

def gerar_badge_veredito(ver):
    ver_str = str(ver).strip().lower()
    if "compra forte" in ver_str:
        cor, bg = "#00cc66", "rgba(0, 204, 102, 0.1)"
    elif "estudo" in ver_str:
        cor, bg = "#f1c40f", "rgba(241, 196, 15, 0.1)"
    else:
        cor, bg = "#bdc3c7", "rgba(189, 195, 199, 0.1)"
        
    estilo = f"border: 1px solid {cor}; color: {cor}; padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: bold; background-color: {bg}; text-transform: uppercase;"
    return f"<span style='{estilo}'>{str(ver).title()}</span>"

def format_money(r, c):
    if pd.isna(r[c]) or r[c] <= 0: return "---"
    simb = "R$" if "Fundamentus" in str(r.get('Origem', '')) else "$"
    return f"{simb} {r[c]:.2f}"

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
                with cols[j]:
                    with st.container(border=True):
                        if ticker in dados_lote.columns and len(dados_lote[ticker].dropna()) >= 2:
                            precos = dados_lote[ticker].dropna()
                            atual = float(precos.iloc[-1])
                            ontem = float(precos.iloc[-2])
                            var = ((atual - ontem) / ontem) * 100
                            
                            if var >= 0:
                                cor_linha = '#00cc66'
                                cor_preenchimento = 'rgba(0, 204, 102, 0.15)'
                                icone_var = "▲"
                                sinal_var = "+"
                            else:
                                cor_linha = '#ff4b4b'
                                cor_preenchimento = 'rgba(255, 75, 75, 0.15)'
                                icone_var = "▼"
                                sinal_var = ""
                                
                            if "^" in ticker or ".SS" in ticker or ".SZ" in ticker or ticker == "000001.SS":
                                unidade = "Pts"
                            elif mercado == "BR" or ticker in ["USDBRL=X", "EURBRL=X"]:
                                unidade = "R$"
                            else:
                                unidade = "US$"
                            
                            min_y = precos.min()
                            max_y = precos.max()
                            margem_y = (max_y - min_y) * 0.1
                            if margem_y == 0: margem_y = max_y * 0.01

                            html_card = f"""
<div style="display: flex; justify-content: space-between; align-items: flex-start; font-family: 'Segoe UI', Arial, sans-serif;">
    <div style="display: flex; flex-direction: column; width: 50%;">
        <span style="color: #ffffff; font-weight: 800; font-size: 15px; line-height: 1.2;">{nome_exibicao}</span>
        <span style="color: #7f8c8d; font-size: 11px; margin-top: 2px;">{ticker}</span>
    </div>
    <div style="display: flex; flex-direction: column; align-items: flex-end; width: 50%;">
        <span style="color: #ffffff; font-weight: bold; font-size: 14px;">{unidade}</span>
        <span style="color: #ffffff; font-weight: 900; font-size: 20px; line-height: 1.1; margin-top: 2px;">{formatar_br(atual, casas)}</span>
        <span style="color: {cor_linha}; font-size: 12px; font-weight: bold; margin-top: 4px;">
            {icone_var} {sinal_var}{var:.2f}%
        </span>
    </div>
</div>
"""
                            st.markdown(html_card, unsafe_allow_html=True)
                            
                            fig = go.Figure(go.Scatter(
                                x=precos.index, 
                                y=precos, 
                                mode='lines', 
                                line=dict(color=cor_linha, width=2.5, shape='spline'), 
                                fill='tozeroy', 
                                fillcolor=cor_preenchimento
                            ))
                            fig.update_layout(
                                template="plotly_dark", 
                                height=65, 
                                margin=dict(l=0,r=0,t=10,b=0), 
                                xaxis_visible=False, 
                                yaxis_visible=False, 
                                yaxis=dict(range=[min_y - margem_y, max_y + margem_y]),
                                showlegend=False, 
                                plot_bgcolor='rgba(0,0,0,0)', 
                                paper_bgcolor='rgba(0,0,0,0)'
                            )
                            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
                            
                            if st.button("🔍 Histórico", key=f"btn_hist_{ticker}_{mercado}", use_container_width=True):
                                abrir_historico_simples(ticker, nome_exibicao)
                                
                            st.caption(f"⚡ {hora_consulta} | {fonte}")
                        
                        else:
                            html_erro = f"""
<div style="display: flex; justify-content: space-between; align-items: flex-start; font-family: 'Segoe UI', Arial, sans-serif; opacity: 0.5;">
    <div style="display: flex; flex-direction: column; width: 100%;">
        <span style="color: #ffffff; font-weight: 800; font-size: 15px; line-height: 1.2;">{nome_exibicao}</span>
        <span style="color: #7f8c8d; font-size: 11px; margin-top: 2px;">{ticker}</span>
        <div style="text-align: center; margin-top: 30px; margin-bottom: 30px;">
            <span style="color: #ff4b4b; font-size: 14px; font-weight: bold;">⚠️ Sem Dados da API</span>
        </div>
    </div>
</div>
"""
                            st.markdown(html_erro, unsafe_allow_html=True)
                            st.caption(f"⚡ YF Timeout")

with aba_macro: renderizar_grid_cards(macro_dict, "Macro")
with aba_br: renderizar_grid_cards(acoes_br_dict, "BR")
with aba_usa: renderizar_grid_cards(acoes_usa_dict, "USA")

# --- MOTOR DE DADOS CENTRAL ---
arquivo_csv = "base_dados.csv"
arquivo_cofre = "cofre_consenso.csv"
dados_base_carregados = False

if os.path.exists(arquivo_csv):
    df = pd.read_csv(arquivo_csv, sep=";")
    df = injetar_precos_ao_vivo(df)
    dados_base_carregados = True
    
    df['Dividendo_Pago'] = df['Preco'] * (df['Div_Yield_%'] / 100)
    df['Teto_Bazin'] = df['Dividendo_Pago'] / 0.06
    df['Margem_Bazin_%'] = np.where(df['Teto_Bazin'] > 0, ((df['Teto_Bazin'] - df['Preco']) / df['Preco']) * 100, 0)
    
    df['Justo_Graham'] = np.where((df['LPA'] > 0) & (df['VPA'] > 0), np.sqrt(22.5 * df['LPA'] * df['VPA']), 0)
    df['Margem_Graham_%'] = np.where(df['Justo_Graham'] > 0, ((df['Justo_Graham'] - df['Preco']) / df['Preco']) * 100, 0)

    if os.path.exists(arquivo_cofre):
        df_cofre = pd.read_csv(arquivo_cofre, sep=";")
        df_cofre = df_cofre.drop_duplicates(subset=['Ticker'], keep='last')
        df = pd.merge(df, df_cofre[['Ticker', 'Val_Pessimista', 'Val_Base', 'Val_Otimista', 'Num_Analistas', 'Recomendacao']], on='Ticker', how='left')
    
    for col in ['Val_Pessimista', 'Val_Base', 'Val_Otimista', 'Num_Analistas']:
        if col not in df.columns: df[col] = 0
        df[col] = df[col].fillna(0)
    
    if 'Recomendacao' not in df.columns: df['Recomendacao'] = 'N/A'
    df['Metodo_Valuation'] = np.where(df['Val_Base'] > 0, "Consenso Analistas", "Sem Cobertura")
    
    df['Margem_Pessimista_%'] = np.where(df['Val_Pessimista'] > 0, ((df['Val_Pessimista'] - df['Preco']) / df['Preco']) * 100, -999)
    df['Margem_Base_%'] = np.where(df['Val_Base'] > 0, ((df['Val_Base'] - df['Preco']) / df['Preco']) * 100, -999)
    df['Margem_Otimista_%'] = np.where(df['Val_Otimista'] > 0, ((df['Val_Otimista'] - df['Preco']) / df['Preco']) * 100, -999)

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

    # --- ABA DE RANKINGS DINÂMICOS ---
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
        df_br = df_rank[df_rank['Origem'].str.contains("Fundamentus|BRAPI", na=False)].copy()
        df_usa = df_rank[~df_rank['Origem'].str.contains("Fundamentus|BRAPI", na=False)].copy()

        def mostrar_tabela_ranking(df_sub, titulo):
            st.subheader(titulo)
            if df_sub.empty:
                st.info("Nenhum ativo atende aos critérios nesta métrica.")
                return
            
            asc = True if filtro_metodo == "Fórmula Mágica (Greenblatt - Foco em Qualidade e Preço)" else False
            df_sub = df_sub.sort_values(by=col_margem, ascending=asc).reset_index(drop=True)
            df_sub.index = df_sub.index + 1
            df_sub['Posição'] = df_sub.index.astype(str) + "º"
            
            html = ESTILO_TABELA_PRO + "<table class='tabela-pro'><thead><tr>"
            html += "<th>Posição</th><th>Ativo</th><th>Preço Atual</th><th>Preço Alvo</th><th>Upside / Margem</th><th>Saúde Visual</th>"
            
            if "Consenso" in filtro_metodo:
                html += "<th>Analistas</th><th>Recomendação</th>"
            html += "</tr></thead><tbody>"

            for idx, row in df_sub.iterrows():
                preco_atual = format_money(row, 'Preco')
                
                if filtro_metodo == "Fórmula Mágica (Greenblatt - Foco em Qualidade e Preço)":
                    preco_alvo = "---"
                    upside_text = f"Score: {row['Pontuacao_Magica']:.0f}"
                    upside_style = "color: #00cc66; font-weight: bold;" 
                else:
                    preco_alvo = format_money(row, col_alvo)
                    upside_val = row[col_margem]
                    if upside_val > 0:
                        upside_text = f"+{upside_val:.2f}%"
                        upside_style = "color: #00cc66; font-weight: bold;" 
                    elif upside_val < 0:
                        upside_text = f"{upside_val:.2f}%"
                        upside_style = "color: #ff4b4b; font-weight: bold;" 
                    else:
                        upside_text = "0.00%"
                        upside_style = "color: #bdc3c7; font-weight: bold;"

                html += "<tr>"
                html += f"<td style='font-weight: bold; color: #ecf0f1;'>{row['Posição']}</td>"
                html += f"<td class='tabela-ativo'>{row['Ticker']}</td>"
                html += f"<td style='font-weight: bold; color: #ecf0f1;'>{preco_atual}</td>"
                html += f"<td style='font-weight: bold; color: #ecf0f1;'>{preco_alvo}</td>"
                html += f"<td style='{upside_style}'>{upside_text}</td>"
                html += f"<td style='font-weight: bold; color: #ecf0f1;'>{row['Saude_Visual']}</td>"
                
                if "Consenso" in filtro_metodo:
                    badge = gerar_badge_recomendacao(row['Recomendacao'])
                    analistas = int(row['Num_Analistas']) if pd.notnull(row['Num_Analistas']) else 0
                    html += f"<td style='font-weight: bold; color: #ecf0f1;'>{analistas}</td><td>{badge}</td>"
                html += "</tr>"

            html += "</tbody></table>"
            st.markdown(html, unsafe_allow_html=True)

        mostrar_tabela_ranking(df_br, "🇧🇷 Top Oportunidades: Brasil")
        mostrar_tabela_ranking(df_usa, "🇺🇸 Top Oportunidades: Wall Street")

    # --- ABA DE VALUATION PRO (TABELA HTML) ---
    with aba_valuation:
        st.header("🧮 Valuation Institucional (Puro Consenso)")
        df_cenarios = df.copy()
        df_cenarios = df_cenarios.sort_values(by='Margem_Base_%', ascending=False).reset_index(drop=True)
        
        html_val = ESTILO_TABELA_PRO + "<table class='tabela-pro'><thead><tr>"
        html_val += "<th>Ativo</th><th>Preço Atual</th><th>🔴 Alvo Pessimista</th><th>🟡 Alvo Base</th><th>🟢 Alvo Otimista</th><th>Analistas</th><th>Recomendação</th><th>Método</th></tr></thead><tbody>"
        
        for idx, row in df_cenarios.iterrows():
            preco_atual = format_money(row, 'Preco')
            alvo_p = format_money(row, 'Val_Pessimista')
            alvo_b = format_money(row, 'Val_Base')
            alvo_o = format_money(row, 'Val_Otimista')
            badge = gerar_badge_recomendacao(row['Recomendacao'])
            analistas = int(row['Num_Analistas']) if pd.notnull(row['Num_Analistas']) else 0
            
            html_val += "<tr>"
            html_val += f"<td class='tabela-ativo'>{row['Ticker']}</td>"
            html_val += f"<td>{preco_atual}</td>"
            html_val += f"<td>{alvo_p}</td>"
            html_val += f"<td>{alvo_b}</td>"
            html_val += f"<td>{alvo_o}</td>"
            html_val += f"<td>{analistas}</td>"
            html_val += f"<td>{badge}</td>"
            html_val += f"<td>{row['Metodo_Valuation']}</td>"
            html_val += "</tr>"
            
        html_val += "</tbody></table>"
        st.markdown(html_val, unsafe_allow_html=True)

    # --- ABA DE FUNDAMENTOS (TABELA HTML) ---
    with aba_fundamentos:
        st.header("Radar de Valor e Qualidade")
        df_fundo = df.copy().sort_values(by='Pontuacao_Magica', ascending=True).reset_index(drop=True)
        
        html_fund = ESTILO_TABELA_PRO + "<table class='tabela-pro'><thead><tr>"
        html_fund += "<th>Ativo</th><th>Preço</th><th>Saúde Visual</th><th>F-Score</th><th>Score Mágico</th><th>ROIC</th><th>ROE</th><th>EV/EBIT</th><th>Div Yield</th><th>Cresc. 5A</th><th>Teto Bazin</th><th>Justo Graham</th></tr></thead><tbody>"
        
        for idx, row in df_fundo.iterrows():
            preco = format_money(row, 'Preco')
            bazin = format_money(row, 'Teto_Bazin')
            graham = format_money(row, 'Justo_Graham')
            
            score_magico = f"{row['Pontuacao_Magica']:.0f}" if pd.notnull(row['Pontuacao_Magica']) and row['Pontuacao_Magica'] > 0 else "---"
            roic = f"{row['ROIC_%']:.2f}%" if pd.notnull(row['ROIC_%']) else "---"
            roe = f"{row['ROE_%']:.2f}%" if pd.notnull(row['ROE_%']) else "---"
            evebit = f"{row['EV_EBIT']:.2f}" if pd.notnull(row['EV_EBIT']) and row['EV_EBIT'] > 0 else "---"
            yield_str = f"{row['Div_Yield_%']:.2f}%" if pd.notnull(row['Div_Yield_%']) else "---"
            cresc = f"{row['Crescimento_5a_%']:.2f}%" if pd.notnull(row['Crescimento_5a_%']) else "---"
            
            html_fund += "<tr>"
            html_fund += f"<td class='tabela-ativo'>{row['Ticker']}</td>"
            html_fund += f"<td>{preco}</td>"
            html_fund += f"<td>{row['Saude_Visual']}</td>"
            html_fund += f"<td>{row['F_Score']}</td>"
            html_fund += f"<td>{score_magico}</td>"
            html_fund += f"<td>{roic}</td>"
            html_fund += f"<td>{roe}</td>"
            html_fund += f"<td>{evebit}</td>"
            html_fund += f"<td>{yield_str}</td>"
            html_fund += f"<td>{cresc}</td>"
            html_fund += f"<td>{bazin}</td>"
            html_fund += f"<td>{graham}</td>"
            html_fund += "</tr>"
            
        html_fund += "</tbody></table>"
        st.markdown(html_fund, unsafe_allow_html=True)

    # --- ABA SIMULADOR (TABELA HTML) ---
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
        else:
            df_sim['Nota_Final'] = 0

        df_sim = df_sim.sort_values(by='Nota_Final', ascending=False).reset_index(drop=True)
        df_sim.index = df_sim.index + 1
        df_sim['Rank'] = df_sim.index.astype(str) + "º"
        df_sim['Veredito'] = pd.cut(df_sim['Nota_Final'], bins=[-1, 40, 75, 100], labels=["Neutro", "Estudo", "Compra Forte"])

        html_sim = ESTILO_TABELA_PRO + "<table class='tabela-pro'><thead><tr>"
        html_sim += "<th>Rank</th><th>Ativo</th><th>Preço Atual</th><th>Nota Final</th><th>Veredito</th><th>Saúde Visual</th></tr></thead><tbody>"
        
        for idx, row in df_sim.iterrows():
            preco_atual = format_money(row, 'Preco')
            nota = f"{row['Nota_Final']:.1f}/100"
            badge_ver = gerar_badge_veredito(row['Veredito'])
            
            html_sim += "<tr>"
            html_sim += f"<td>{row['Rank']}</td>"
            html_sim += f"<td class='tabela-ativo'>{row['Ticker']}</td>"
            html_sim += f"<td>{preco_atual}</td>"
            html_sim += f"<td>{nota}</td>"
            html_sim += f"<td>{badge_ver}</td>"
            html_sim += f"<td>{row['Saude_Visual']}</td>"
            html_sim += "</tr>"
            
        html_sim += "</tbody></table>"
        st.markdown(html_sim, unsafe_allow_html=True)

else: 
    st.warning("⚠️ Execute o 'robo_balancos.py' primeiro.")

# --- ABA DE ANÁLISES (MODAL INSTITUCIONAL) ---
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
        gerar_relatorio_ia_dashboard(ativo_selecionado, dados_envio)
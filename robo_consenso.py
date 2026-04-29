import yfinance as yf
import pandas as pd
import requests
import time
import os
import sys
import re
from datetime import datetime
import logging
import warnings

# --- SILENCIADORES ---
warnings.filterwarnings("ignore")
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

print("======================================================")
print("🤖 ROBÔ DE CONSENSO (V9 - O INVASOR DE CATRACAS)")
print("======================================================\n")

arquivo_base = "base_dados.csv"
arquivo_cofre = "cofre_consenso.csv"

if not os.path.exists(arquivo_base):
    print("❌ ERRO: 'base_dados.csv' não encontrado.")
    sys.exit()

df_base = pd.read_csv(arquivo_base, sep=";")
tickers_para_pesquisar = df_base['Ticker'].unique().tolist()
print(f"🎯 Total de ativos na carteira: {len(tickers_para_pesquisar)}")

# --- LER O COFRE EXISTENTE E AVALIAR VALIDADE (30 DIAS) ---
cofre_atual = {}
if os.path.exists(arquivo_cofre):
    df_cofre = pd.read_csv(arquivo_cofre, sep=";")
    for _, row in df_cofre.iterrows():
        try:
            data_str = row['Data_Atualizacao']
            data_obj = datetime.strptime(data_str, "%d/%m/%Y %H:%M:%S")
            if (datetime.now() - data_obj).days <= 30 and row['Val_Base'] > 0:
                cofre_atual[row['Ticker']] = row.to_dict()
        except Exception:
            pass

print(f"🛡️  Ativos válidos já no cofre (menos de 30 dias): {len(cofre_atual)}\n")

novos_dados_cofre = []
hora_atualizacao = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5'
}

# --- O FALSIFICADOR DE CRACHÁS (CRUMB) ---
def forjar_cracha_yahoo():
    sessao = requests.Session()
    sessao.headers.update(HEADERS)
    print("🕵️‍♂️  Forjando crachá de acesso (Crumb) no Yahoo Finance...", end=" ")
    try:
        # 1. Visita a recepção para pegar o Cookie
        sessao.get('https://finance.yahoo.com', timeout=10)
        time.sleep(1)
        
        # 2. Vai na segurança pegar o Crumb
        res_crumb = sessao.get('https://query1.finance.yahoo.com/v1/test/getcrumb', timeout=5)
        
        if res_crumb.status_code == 200 and res_crumb.text:
            # Pega o texto do crachá
            print(f"✅ Sucesso! Crachá obtido: [{res_crumb.text[:4]}***]\n")
            return sessao, res_crumb.text
        else:
            print("❌ Falha. Vamos tentar sem crachá mesmo.\n")
            return sessao, None
    except Exception as e:
        print(f"❌ Erro ao forjar: {e}\n")
        return sessao, None

# Inicia a sessão com o crachá antes do loop
SESSAO_GLOBAL, CRACHA_GLOBAL = forjar_cracha_yahoo()

def aguardar_com_timer(segundos, motivo_erro):
    print(f"      ↳ ⚠️ Erro real: {motivo_erro}")
    for i in range(segundos, 0, -1):
        sys.stdout.write(f"\r      ↳ ⏳ Esfriando conexão... Retomando em {i}s ")
        sys.stdout.flush()
        time.sleep(1)
    sys.stdout.write("\r      ↳ ✅ Retomando operação...                 \n")
    sys.stdout.flush()

def tentar_raspar_yahoo(ticker_formatado, sessao, crumb):
    # Se temos o crachá, mostramos na URL. Senão, tenta sem.
    if crumb:
        url_oculta = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker_formatado}?modules=financialData&crumb={crumb}"
    else:
        url_oculta = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker_formatado}?modules=financialData"
        
    # Usa a 'sessao' em vez de 'requests' solto, para levar o adesivo de visitante (Cookies) junto
    res = sessao.get(url_oculta, timeout=5) 
    res.raise_for_status() 
    
    fin_data = res.json().get('quoteSummary', {}).get('result', [{}])[0].get('financialData', {})
    val_base = fin_data.get('targetMeanPrice', {}).get('raw', 0)
    if val_base > 0:
        return {
            'Val_Base': val_base,
            'Val_Pessimista': fin_data.get('targetLowPrice', {}).get('raw', 0),
            'Val_Otimista': fin_data.get('targetHighPrice', {}).get('raw', 0),
            'Num_Analistas': fin_data.get('numberOfAnalystOpinions', {}).get('raw', 0),
            'Recomendacao': fin_data.get('recommendationKey', 'N/A').replace('_', ' ').title(),
            'Fonte': "Scraping Hacker (Crumb)"
        }
    return None

try:
    for i, ticker in enumerate(tickers_para_pesquisar, 1):
        ticker_limpo = str(ticker).strip()
        print(f"[{i}/{len(tickers_para_pesquisar)}] {ticker_limpo}...", end=" ")

        if ticker_limpo in cofre_atual:
            print("✅ Pulado (Dado recente no Cofre)")
            novos_dados_cofre.append(cofre_atual[ticker_limpo])
            continue

        is_br = False
        ticker_yahoo = ticker_limpo
        if re.match(r'^[A-Z]{4}\d{1,2}$', ticker_yahoo) or ticker_yahoo.endswith('.SA'):
            is_br = True
            if not ticker_yahoo.endswith('.SA'):
                ticker_yahoo = f"{ticker_yahoo}.SA"

        dado_encontrado = None
        erro_capturado = "Sem Dados (Vazio)"
        erro_fatal = False 

        # --- LÓGICA EUA ---
        if not is_br:
            try:
                info = yf.Ticker(ticker_yahoo).info
                if info.get('targetMeanPrice', 0) > 0:
                    dado_encontrado = {
                        'Val_Base': info.get('targetMeanPrice'),
                        'Val_Pessimista': info.get('targetLowPrice', 0),
                        'Val_Otimista': info.get('targetHighPrice', 0),
                        'Num_Analistas': info.get('numberOfAnalystOpinions', 0),
                        'Recomendacao': str(info.get('recommendationKey', 'N/A')).replace('_', ' ').title(),
                        'Fonte': "API Oficial"
                    }
            except Exception:
                pass
            time.sleep(0.5)

        # --- LÓGICA BRASIL ---
        else:
            tentativas = 2
            for tentativa in range(1, tentativas + 1):
                try:
                    info = yf.Ticker(ticker_yahoo).info
                    if info.get('targetMeanPrice', 0) > 0:
                        dado_encontrado = {
                            'Val_Base': info.get('targetMeanPrice'),
                            'Val_Pessimista': info.get('targetLowPrice', 0),
                            'Val_Otimista': info.get('targetHighPrice', 0),
                            'Num_Analistas': info.get('numberOfAnalystOpinions', 0),
                            'Recomendacao': str(info.get('recommendationKey', 'N/A')).replace('_', ' ').title(),
                            'Fonte': "API Oficial"
                        }
                        break 
                    
                    # Usa o crachá forjado para invadir a sala
                    resultado_scraping = tentar_raspar_yahoo(ticker_yahoo, SESSAO_GLOBAL, CRACHA_GLOBAL)
                    if resultado_scraping:
                        dado_encontrado = resultado_scraping
                        break 
                    else:
                        erro_capturado = "Ativo não possui cobertura no Yahoo."
                        erro_fatal = True
                        break

                except Exception as e:
                    erro_capturado = str(e)[:60] + "..."
                    # Se der 401 agora mesmo com crachá, ou 404, não espera.
                    if "401" in erro_capturado or "404" in erro_capturado:
                        erro_fatal = True
                        break 

                if tentativa < tentativas and not erro_fatal:
                    print(f"❌ Falha (Tentativa {tentativa}/{tentativas})")
                    aguardar_com_timer(60, erro_capturado)
                    print(f"      ↳ Retentando {ticker_limpo}...", end=" ")

            if not dado_encontrado and not erro_fatal:
                print(f"❌ Falha de Rede.")
                aguardar_com_timer(30, erro_capturado)
            elif not dado_encontrado and erro_fatal:
                pass 

        # --- MONTAR E SALVAR ---
        if dado_encontrado:
            print(f"✅ Salvo ({dado_encontrado['Fonte']})")
        else:
            if "401" in erro_capturado or "404" in erro_capturado or "não possui" in erro_capturado:
                print(f"➖ Acesso Negado/Sem Cobertura (Ignorando timer).")
            else:
                print(f"➖ Sem dados após falhas.")
            
            dado_encontrado = {
                'Val_Base': 0, 'Val_Pessimista': 0, 'Val_Otimista': 0,
                'Num_Analistas': 0, 'Recomendacao': 'N/A', 'Fonte': 'Sem Cobertura'
            }

        novos_dados_cofre.append({
            'Ticker': ticker_limpo,
            'Val_Pessimista': dado_encontrado['Val_Pessimista'],
            'Val_Base': dado_encontrado['Val_Base'],
            'Val_Otimista': dado_encontrado['Val_Otimista'],
            'Num_Analistas': dado_encontrado['Num_Analistas'],
            'Recomendacao': dado_encontrado['Recomendacao'],
            'Data_Atualizacao': hora_atualizacao,
            'Fonte': dado_encontrado['Fonte']
        })

except KeyboardInterrupt:
    print("\n\n🛑 INTERROMPIDO PELO USUÁRIO (Ctrl + C)!")
    print("Salvando o progresso atual no Cofre...")

# --- CONSOLIDAR COFRE ---
if novos_dados_cofre:
    df_final = pd.DataFrame(novos_dados_cofre)
    df_final.to_csv(arquivo_cofre, sep=";", index=False)
    print("\n💾 Arquivo 'cofre_consenso.csv' salvo com sucesso!")
else:
    print("\nNenhum dado salvo.")
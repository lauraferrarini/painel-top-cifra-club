import requests
from bs4 import BeautifulSoup
import json
import os
import glob
import sys
import traceback
from datetime import datetime
from urllib.parse import urljoin

# Configurações Gerais
PASTA_DADOS = "historico_dados"
PASTA_RELATORIOS = "historico_relatorios"
MARGEM_OSCILACAO = 2 

# Mapeamento do Cifra Club (Top Único)
REGIOES = {
    "cc": {"nome": "Cifra Club", "url": "https://www.cifraclub.com.br/mais-acessadas/", "cookies": {}}
}

def extrair_musicas(url, cookies):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7'
    }
    response = requests.get(url, headers=headers, cookies=cookies, timeout=15)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.text, 'html.parser')
    musicas_atuais = {}
    
    # Mapeia especificamente a lista ordenada de músicas do Cifra Club pelo id 'js-sng_list'
    lista_top = soup.find('ol', id='js-sng_list') or soup.find('ol', class_=lambda c: c and ('top' in c or 'gridMusicTop' in c))
    
    if not lista_top:
        return musicas_atuais
        
    itens = lista_top.find_all('li')
    for rank, item in enumerate(itens, start=1):
        tag_nome = item.find('strong', class_=lambda c: c and 'top-txt_primary' in c) or item.find(['strong', 'b'])
        tag_artista = item.find('span', class_='top-txt_secondary') or item.find('span')
        tag_a = item.find('a')
        
        nome = tag_nome.text.strip() if tag_nome else "Desconhecido"
        artista = tag_artista.text.strip() if tag_artista else "Desconhecido"
        
        # Garante que não inserimos itens vazios ou desalinhados
        if nome == "Desconhecido" and not tag_a:
            continue

        # Captura o link relativo e transforma em URL absoluta funcional
        href = tag_a['href'] if tag_a and tag_a.has_attr('href') else ""
        link_absoluto = urljoin(url, href) if href else ""
        
        chave = f"{nome} - {artista}"
        musicas_atuais[chave] = {
            "posicao": rank,
            "nome": nome,
            "artista": artista,
            "url": link_absoluto
        }
            
    return musicas_atuais

def buscar_dados_anteriores(regiao):
    data_hoje_iso = datetime.now().strftime("%Y-%m-%d")
    pasta_regiao = os.path.join(PASTA_DADOS, regiao)
    
    if os.path.exists(pasta_regiao):
        arquivos = sorted([
            f for f in os.listdir(pasta_regiao) 
            if f.endswith('.json') and f != f"dados_{data_hoje_iso}.json"
        ])
        if arquivos:
            ultimo_arquivo = os.path.join(pasta_regiao, arquivos[-1])
            with open(ultimo_arquivo, 'r', encoding='utf-8') as f:
                return json.load(f)
    return {}

def atualizar_dados_dashboard(regiao):
    pasta_regiao = os.path.join(PASTA_DADOS, regiao)
    arquivos = sorted(glob.glob(os.path.join(pasta_regiao, "dados_*.json")))
    historico_global = {}
    todas_datas = []
    
    for arq in arquivos:
        nome_base = os.path.basename(arq)
        data_str = nome_base.replace("dados_", "").replace(".json", "")
        todas_datas.append(data_str)
        
        with open(arq, 'r', encoding='utf-8') as f:
            dados_dia = json.load(f)
            
        for chave, info in dados_dia.items():
            if chave not in historico_global:
                historico_global[chave] = {}
            # Preserva a URL estável da música dentro da estrutura estruturada do Dashboard
            if "url" in info and "url" not in historico_global[chave]:
                historico_global[chave]["url"] = info["url"]
            historico_global[chave][data_str] = info["posicao"]
            
    dados_finais = {
        "datas": todas_datas,
        "musicas": historico_global
    }
    
    with open(f"dados_dashboard_{regiao}.json", "w", encoding="utf-8") as f:
        json.dump(dados_finais, f, ensure_ascii=False, indent=4)

def processar_regiao(regiao, config):
    print(f"🌍 Coletando dados: {config['nome']} ({regiao})...")
    
    # Garante as subpastas específicas
    pasta_dados_regiao = os.path.join(PASTA_DADOS, regiao)
    pasta_relatorios_regiao = os.path.join(PASTA_RELATORIOS, regiao)
    os.makedirs(pasta_dados_regiao, exist_ok=True)
    os.makedirs(pasta_relatorios_regiao, exist_ok=True)
    
    atuais = extrair_musicas(config['url'], config['cookies'])
    if not atuais:
        print(f"⚠️ Alerta: Nenhuma música coletada para {config['nome']}. Estrutura mudou ou bloqueio.")
        return False
        
    anteriores = buscar_dados_anteriores(regiao)
    
    data_hoje_iso = datetime.now().strftime("%Y-%m-%d")
    data_hoje_br = datetime.now().strftime("%d/%m/%Y")

    novas_entradas = []
    subidas_absurdas = []   
    grandes_saltos = []     
    subidas_moderadas = []  
    pequenas_subidas = []   

    if not anteriores:
        conteudo_md = f"# 📊 Relatório Cifra Club - {config['nome']} - {data_hoje_br}\n\n"
        conteudo_md += f"ℹ️ **Base de dados de {config['nome']} estruturada com sucesso hoje!**\n"
        conteudo_md += "As movimentações e gráficos interativos começarão a rodar a partir do próximo ciclo de coleta.\n\n"
        conteudo_md += "### 📋 Prévia do Top 10 Atual:\n"
        for i, (chave, m) in enumerate(atuais.items(), start=1):
            if i > 10: break
            conteudo_md += f"{i}º. **{m['nome']}** — *{m['artista']}*\n"
    else:
        for chave, dados_atuais in atuais.items():
            pos_atual = dados_atuais['posicao']
            
            if chave not in anteriores:
                novas_entradas.append(dados_atuais)
            else:
                pos_anterior = anteriores[chave]['posicao']
                diferenca = pos_anterior - pos_atual 
                
                dados_item = {
                    "dados": dados_atuais,
                    "pos_anterior": pos_anterior,
                    "pos_atual": pos_atual,
                    "posicoes_ganhas": diferenca
                }

                if diferenca > 400:
                    subidas_absurdas.append(dados_item)
                elif diferenca > 200:
                    grandes_saltos.append(dados_item)
                elif diferenca >= 100:
                    subidas_moderadas.append(dados_item)
                elif diferenca > MARGEM_OSCILACAO:
                    pequenas_subidas.append(dados_item)

        subidas_absurdas.sort(key=lambda x: x['posicoes_ganhas'], reverse=True)
        grandes_saltos.sort(key=lambda x: x['posicoes_ganhas'], reverse=True)
        subidas_moderadas.sort(key=lambda x: x['posicoes_ganhas'], reverse=True)
        pequenas_subidas.sort(key=lambda x: x['posicoes_ganhas'], reverse=True)

        conteudo_md = f"# 📊 Relatório Cifra Club - {config['nome']} - {data_hoje_br}\n\n"
        
        if subidas_absurdas:
            conteudo_md += "## 🚨 🚨 EXPLOSÃO NO TOP: SUBIDAS ABSURDAS (+400 posições) 🚨 🚨\n"
            for m in subidas_absurdas:
                conteudo_md += f"> ### 💥 **{m['dados']['nome']}** — *{m['dados']['artista']}*\n"
                conteudo_md += f"> 🛑 **Subida histórica!** Saltou de {m['pos_anterior']}º direto para **{m['pos_atual']}º** (🔼 **+{m['posicoes_ganhas']}** posições)\n\n"
        
        conteudo_md += "## 🔥 Grandes Saltos (+200 a 400 posições)\n"
        if grandes_saltos:
            for m in grandes_saltos:
                conteudo_md += f"- **{m['dados']['nome']}** ({m['dados']['artista']}): Subiu de {m['pos_anterior']}º para **{m['pos_atual']}º** (🔥 +{m['posicoes_ganhas']} posições)\n"
        else:
            conteudo_md += "- Nenhuma música com grande salto nesta faixa hoje.\n"

        conteudo_md += "\n## 📈 Subidas Significativas (100 a 200 posições)\n"
        if subidas_moderadas:
            for m in subidas_moderadas:
                conteudo_md += f"- **{m['dados']['nome']}** ({m['dados']['artista']}): Subiu de {m['pos_anterior']}º para **{m['pos_atual']}º** (📈 +{m['posicoes_ganhas']} posições)\n"
        else:
            conteudo_md += "- Nenhuma subida nesta faixa hoje.\n"

        conteudo_md += f"\n## 🌱 Pequenas Subidas (Abaixo de 100 posições)\n"
        conteudo_md += f"> Omitindo oscilações menores ou iguais a {MARGEM_OSCILACAO} posições.\n\n"
        if pequenas_subidas:
            for m in pequenas_subidas:
                conteudo_md += f"- **{m['dados']['nome']}** ({m['dados']['artista']}): {m['pos_anterior']}º → **{m['pos_atual']}º** (+{m['posicoes_ganhas']})\n"
        else:
            conteudo_md += "- Sem oscilações relevantes para cima hoje.\n"

        conteudo_md += "\n## 🚀 Novas Entradas no Top\n"
        if novas_entradas:
            for m in novas_entradas:
                conteudo_md += f"- **{m['nome']}** ({m['artista']}) - Apareceu direto na posição **{m['posicao']}º**\n"
        else:
            conteudo_md += "- Nenhuma música inédita detectada hoje.\n"

    # Salva os relatórios específicos
    with open(os.path.join(pasta_relatorios_regiao, f"relatorio_{data_hoje_iso}.md"), 'w', encoding='utf-8') as f:
        f.write(conteudo_md)
        
    # Relatório raiz específico
    with open(f"relatorio_diario_{regiao}.md", 'w', encoding='utf-8') as f:
        f.write(conteudo_md)
        
    # Salva o JSON na subpasta correspondente
    with open(os.path.join(pasta_dados_regiao, f"dados_{data_hoje_iso}.json"), 'w', encoding='utf-8') as f:
        json.dump(atuais, f, ensure_ascii=False, indent=4)
        
    return True

if __name__ == "__main__":
    try:
        sucesso_geral = True
        for regiao, config in REGIOES.items():
            try:
                if processar_regiao(regiao, config):
                    atualizar_dados_dashboard(regiao)
                    print(f"✅ Fonte {regiao.upper()} processada com sucesso.\n")
                else:
                    sucesso_geral = False
            except Exception as e:
                print(f"\n💥 Erro ao processar {regiao.upper()}:")
                traceback.print_exc()
                sucesso_geral = False
        
        if sucesso_geral:
            print("🚀 Módulo executado com sucesso total!")
        else:
            print("⚠️ Execução concluída com falhas parciais.")
            sys.exit(1)
            
    except Exception as e:
        print("\n💥 --- ERRO CRÍTICO INESPERADO NO SCRIPT --- 💥")
        traceback.print_exc()
        sys.exit(1)

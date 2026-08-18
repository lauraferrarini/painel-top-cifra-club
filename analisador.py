import requests
import json
import os
import glob
import sys
import traceback
from datetime import datetime
from urllib.parse import urlparse

# Configurações Gerais
PASTA_DADOS = "historico_dados"
PASTA_RELATORIOS = "historico_relatorios"
MARGEM_OSCILACAO = 2

# Mapeamento de Regiões e endpoints da API do Cifra Club
REGIOES = {
    "br": {"nome": "Brasil", "url": "https://api.cifraclub.com.br/v3/top/songs?limit=1000"},
    "hispam": {"nome": "Hispam", "url": "https://api.cifraclub.com.br/v3/top/songs?lang=es&limit=1000"}
}

def extrair_musicas(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Accept': 'application/json'
    }
    response = requests.get(url, headers=headers, timeout=20)
    response.raise_for_status()

    dados = response.json()
    lista_songs = dados.get('songs', []) or []
    musicas_atuais = {}

    for rank, item in enumerate(lista_songs, start=1):
        nome = (item.get('name') or "Desconhecido").strip()
        artista_obj = item.get('artist') or {}
        artista = (artista_obj.get('name') or "Desconhecido").strip()

        # Monta a URL absoluta da música juntando o slug do artista com o
        # slug da música (é assim que o Cifra Club estrutura os links).
        artista_slug = artista_obj.get('url') or ""
        musica_slug = item.get('url') or ""
        link_absoluto = f"https://www.cifraclub.com.br/{artista_slug}/{musica_slug}/" if (artista_slug and musica_slug) else ""

        # ⚡ ID ESTÁVEL: a API do Cifra Club já entrega um id numérico único e
        # permanente por música (item['id']), então ele é usado direto como
        # chave — o mesmo id aparece tanto no top do Brasil quanto no top do
        # Hispam pra mesma música, o que é o que permite o cruzamento entre
        # regiões ("Também aparece em") no index.html encontrar a outra
        # região, sem nenhuma lógica extra de casamento por caminho/texto
        # (diferente do robô antigo, que precisava disso porque fazia
        # scraping de HTML sem id estável). Só cai pro caminho da URL, e por
        # último pro formato antigo (Nome - Artista), se a API vier sem id.
        song_id = item.get('id')
        if song_id is not None:
            chave = str(song_id)
        elif link_absoluto:
            chave = urlparse(link_absoluto).path
        else:
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

        # A chave do dia já é o id estável da música (vindo direto da API),
        # então ela mesma é a "bucket" definitiva dentro de historico_global
        # — sem precisar da lógica de casamento por caminho/texto que o robô
        # antigo usava pra compensar o scraping de HTML sem id.
        for chave, info in dados_dia.items():
            if chave not in historico_global:
                historico_global[chave] = {}

            if info.get("url"):
                historico_global[chave]["url"] = info["url"]
            if info.get("nome"):
                historico_global[chave]["nome"] = info["nome"]
            if info.get("artista"):
                historico_global[chave]["artista"] = info["artista"]

            historico_global[chave][data_str] = info["posicao"]

    dados_finais = {
        "datas": todas_datas,
        "musicas": historico_global
    }

    with open(f"dados_dashboard_{regiao}.json", "w", encoding="utf-8") as f:
        json.dump(dados_finais, f, ensure_ascii=False, indent=4)

def processar_regiao(regiao, config):
    print(f"🎸 Coletando dados da região: {config['nome']} ({regiao})...")

    pasta_dados_regiao = os.path.join(PASTA_DADOS, regiao)
    pasta_relatorios_regiao = os.path.join(PASTA_RELATORIOS, regiao)
    os.makedirs(pasta_dados_regiao, exist_ok=True)
    os.makedirs(pasta_relatorios_regiao, exist_ok=True)

    atuais = extrair_musicas(config['url'])
    if not atuais:
        print(f"⚠️ Alerta: Nenhuma música coletada para {config['nome']}. API mudou ou bloqueio.")
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
            info_anterior = anteriores.get(chave)

            if info_anterior is None:
                novas_entradas.append(dados_atuais)
            else:
                pos_anterior = info_anterior['posicao']
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

    # Salva os relatórios específicos da região
    with open(os.path.join(pasta_relatorios_regiao, f"relatorio_{data_hoje_iso}.md"), 'w', encoding='utf-8') as f:
        f.write(conteudo_md)

    # Relatório raiz específico da região (ex: relatorio_diario_hispam.md)
    with open(f"relatorio_diario_{regiao}.md", 'w', encoding='utf-8') as f:
        f.write(conteudo_md)

    # Salva o JSON na subpasta correspondente
    with open(os.path.join(pasta_dados_regiao, f"dados_{data_hoje_iso}.json"), 'w', encoding='utf-8') as f:
        json.dump(atuais, f, ensure_ascii=False, indent=4)

    return True

if __name__ == "__main__":
    try:
        # Define o alvo baseado no argumento do terminal (ex: "br", "hispam", ou "all")
        alvo = sys.argv[1].lower() if len(sys.argv) > 1 else "all"

        if alvo == "br":
            regioes_para_processar = ["br"]
        elif alvo == "hispam":
            regioes_para_processar = ["hispam"]
        else:
            regioes_para_processar = list(REGIOES.keys())

        print(f"🚀 Iniciando módulo de análise para o alvo: {alvo.upper()}")

        sucesso_geral = True
        for regiao in regioes_para_processar:
            config = REGIOES[regiao]
            try:
                if processar_regiao(regiao, config):
                    atualizar_dados_dashboard(regiao)
                    print(f"✅ Região {regiao.upper()} processada com sucesso.\n")
                else:
                    sucesso_geral = False
            except Exception as e:
                print(f"\n💥 Erro ao processar a região {regiao.upper()}:")
                traceback.print_exc()
                sucesso_geral = False

        if sucesso_geral:
            print(f"🚀 Módulo executado com sucesso total para as regiões ({alvo.upper()})!")
        else:
            print("⚠️ Execução concluída com falhas parciais em algumas regiões.")
            sys.exit(1)

    except Exception as e:
        print("\n💥 --- ERRO CRÍTICO INESPERADO NO SCRIPT --- 💥")
        traceback.print_exc()
        sys.exit(1)

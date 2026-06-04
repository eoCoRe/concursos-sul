"""
Scraper para PCI Concursos - Região Sul (SC, PR, RS)
Extrai: órgão, vagas, salário, nível, estado, data limite
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re
import logging
from datetime import datetime
from database import salvar_concursos

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

ESTADOS_SUL = {"SC", "PR", "RS"}

URLS_REGIAO_SUL = [
    "https://www.pciconcursos.com.br/concursos/sul/",
    "https://www.pciconcursos.com.br/concursos/sul/pagina2/",
    "https://www.pciconcursos.com.br/concursos/sul/pagina3/",
]


def extrair_salario(texto: str) -> float | None:
    """Converte 'R$ 5.400,00' ou 'R$5400' para float."""
    numeros = re.findall(r"[\d\.]+,\d{2}", texto)
    if numeros:
        valor = numeros[0].replace(".", "").replace(",", ".")
        try:
            return float(valor)
        except ValueError:
            pass
    numeros_simples = re.findall(r"\d{3,}", texto)
    if numeros_simples:
        try:
            return float(numeros_simples[0])
        except ValueError:
            pass
    return None


def extrair_vagas(texto: str) -> int | None:
    numeros = re.findall(r"\d+", texto.replace(".", ""))
    if numeros:
        try:
            return int(numeros[0])
        except ValueError:
            pass
    return None


def detectar_nivel(texto: str) -> str:
    texto_lower = texto.lower()
    if any(p in texto_lower for p in ["superior", "graduação", "tecnólogo", "tecnologia"]):
        return "Superior"
    if any(p in texto_lower for p in ["médio", "medio", "técnico"]):
        return "Médio"
    if "fundamental" in texto_lower:
        return "Fundamental"
    return "Não informado"


def raspar_pagina(url: str) -> list[dict]:
    """Faz o scraping de uma página do PCI Concursos e retorna lista de dicts."""
    concursos = []
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except requests.RequestException as e:
        log.error(f"Erro ao acessar {url}: {e}")
        return concursos

    soup = BeautifulSoup(response.text, "html.parser")

    # PCI Concursos lista concursos em <article> ou linhas de tabela
    # Tentamos os dois padrões comuns do site
    items = soup.select("article.cn") or soup.select("div.cn") or soup.select("li.cn")

    if not items:
        # Fallback: procura por links que parecem concursos
        items = soup.select("a[href*='/concurso/']")

    log.info(f"Encontrados {len(items)} itens em {url}")

    for item in items:
        try:
            texto_completo = item.get_text(" ", strip=True)

            # Órgão: primeiro texto em negrito ou título do link
            orgao_tag = item.select_one("strong, b, h2, h3, .cn-titulo")
            orgao = orgao_tag.get_text(strip=True) if orgao_tag else item.get_text(strip=True)[:80]

            # Estado (busca sigla de 2 letras no texto ou na URL)
            estado = "Não informado"
            match_estado = re.search(r"\b(SC|PR|RS)\b", texto_completo)
            if match_estado:
                estado = match_estado.group(1)

            # Salário
            salario = None
            match_salario = re.search(r"R\$\s*[\d\.]+,\d{2}", texto_completo)
            if match_salario:
                salario = extrair_salario(match_salario.group())

            # Vagas
            vagas = None
            match_vagas = re.search(r"(\d+)\s*vaga", texto_completo, re.IGNORECASE)
            if match_vagas:
                vagas = int(match_vagas.group(1))

            # Nível
            nivel = detectar_nivel(texto_completo)

            # Data limite
            data_limite = None
            match_data = re.search(r"\d{2}/\d{2}/\d{4}", texto_completo)
            if match_data:
                try:
                    data_limite = datetime.strptime(match_data.group(), "%d/%m/%Y").date().isoformat()
                except ValueError:
                    pass

            # Link do edital
            link_tag = item.select_one("a[href]")
            link = link_tag["href"] if link_tag else ""
            if link and not link.startswith("http"):
                link = "https://www.pciconcursos.com.br" + link

            concursos.append(
                {
                    "orgao": orgao,
                    "estado": estado,
                    "vagas": vagas,
                    "salario": salario,
                    "nivel": nivel,
                    "data_limite": data_limite,
                    "link": link,
                    "coletado_em": datetime.now().isoformat(),
                }
            )
        except Exception as e:
            log.warning(f"Erro ao processar item: {e}")
            continue

    return concursos


def coletar_todos() -> pd.DataFrame:
    """Raspa todas as páginas da região Sul e retorna DataFrame consolidado."""
    todos = []
    for url in URLS_REGIAO_SUL:
        log.info(f"Raspando: {url}")
        resultado = raspar_pagina(url)
        todos.extend(resultado)
        time.sleep(2)  # pausa educada entre requisições

    if not todos:
        log.warning("Nenhum concurso encontrado. Verifique a conexão ou a estrutura do site.")
        return pd.DataFrame()

    df = pd.DataFrame(todos)

    # Remove duplicatas pelo link
    df.drop_duplicates(subset=["link"], inplace=True)

    log.info(f"Total coletado: {len(df)} concursos")
    return df


if __name__ == "__main__":
    df = coletar_todos()
    if not df.empty:
        salvar_concursos(df)
        print(f"\n✓ {len(df)} concursos salvos no banco.")
        print(df[["orgao", "estado", "vagas", "salario", "nivel", "data_limite"]].to_string(index=False))
    else:
        print("Nenhum dado coletado.")

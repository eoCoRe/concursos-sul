"""
Scraper para PCI Concursos - Região Sul (SC, PR, RS)
Estrutura real do site: .ca (item) > .cc (estado) > .cd (vagas/salário/nível) > .ce (data)
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


def _paginas_sul() -> list[str]:
    """Descobre quantas páginas existem e retorna todas as URLs."""
    base = "https://www.pciconcursos.com.br/concursos/sul/"
    urls = [base]
    try:
        r = requests.get(base, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        # Paginação do PCI: links com padrão /concursos/sul/paginaN/
        paginas = set()
        for a in soup.select("a[href*='/concursos/sul/pagina']"):
            m = re.search(r"pagina(\d+)", a["href"])
            if m:
                paginas.add(int(m.group(1)))
        for n in sorted(paginas):
            urls.append(f"{base}pagina{n}/")
    except Exception as e:
        log.warning(f"Não conseguiu descobrir paginação: {e}")
    return urls


def _extrair_salario(texto: str) -> float | None:
    # Pega o maior valor R$ encontrado (geralmente é o teto)
    valores = re.findall(r"R\$\s*([\d\.]+,\d{2})", texto)
    resultados = []
    for v in valores:
        try:
            resultados.append(float(v.replace(".", "").replace(",", ".")))
        except ValueError:
            pass
    return max(resultados) if resultados else None


def _detectar_nivel(texto: str) -> str:
    t = texto.lower()
    partes = []
    if any(p in t for p in ["superior", "graduação", "tecnólogo", "tecnol"]):
        partes.append("Superior")
    if any(p in t for p in ["médio", "medio", "técnico", "tecnico"]):
        partes.append("Médio")
    if "fundamental" in t:
        partes.append("Fundamental")
    return " / ".join(partes) if partes else "Não informado"


def raspar_pagina(url: str) -> list[dict]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        r.encoding = "utf-8"
    except requests.RequestException as e:
        log.error(f"Erro ao acessar {url}: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    items = soup.select("div.ca")
    log.info(f"{url} → {len(items)} concursos")

    concursos = []
    for item in items:
        try:
            # Órgão e link
            link_tag = item.select_one("a[href]")
            orgao = link_tag.get_text(strip=True) if link_tag else "Não informado"
            link = link_tag["href"] if link_tag else ""
            if link and not link.startswith("http"):
                link = "https://www.pciconcursos.com.br" + link

            # Estado (.cc)
            estado_tag = item.select_one(".cc")
            estado = estado_tag.get_text(strip=True) if estado_tag else "Não informado"

            # Vagas, salário, cargos, nível (.cd)
            cd_tag = item.select_one(".cd")
            cd_texto = cd_tag.get_text(" ", strip=True) if cd_tag else ""

            vagas = None
            m_vagas = re.search(r"(\d+)\s*vaga", cd_texto, re.IGNORECASE)
            if m_vagas:
                vagas = int(m_vagas.group(1))

            salario = _extrair_salario(cd_texto)
            nivel = _detectar_nivel(cd_texto)

            # Cargos: primeiro <span> dentro de .cd
            cargo_tag = cd_tag.select_one("span") if cd_tag else None
            cargo = cargo_tag.get_text(" ", strip=True).split("\n")[0].strip() if cargo_tag else ""

            # Data limite (.ce)
            ce_tag = item.select_one(".ce")
            data_limite = None
            if ce_tag:
                m_data = re.search(r"(\d{2}/\d{2}/\d{4})", ce_tag.get_text())
                if m_data:
                    try:
                        data_limite = datetime.strptime(m_data.group(1), "%d/%m/%Y").date().isoformat()
                    except ValueError:
                        pass

            concursos.append({
                "orgao": orgao,
                "estado": estado,
                "vagas": vagas,
                "salario": salario,
                "nivel": nivel,
                "cargo": cargo,
                "data_limite": data_limite,
                "link": link,
                "coletado_em": datetime.now().isoformat(),
            })
        except Exception as e:
            log.warning(f"Erro ao processar item: {e}")

    return concursos


def coletar_todos() -> pd.DataFrame:
    urls = _paginas_sul()
    log.info(f"Total de páginas encontradas: {len(urls)}")

    todos = []
    for url in urls:
        todos.extend(raspar_pagina(url))
        time.sleep(1.5)

    if not todos:
        log.warning("Nenhum concurso encontrado.")
        return pd.DataFrame()

    df = pd.DataFrame(todos)
    df.drop_duplicates(subset=["link"], inplace=True)
    log.info(f"Total único coletado: {len(df)} concursos")
    return df


if __name__ == "__main__":
    df = coletar_todos()
    if not df.empty:
        salvar_concursos(df)
        print(f"\nOK: {len(df)} concursos salvos no banco.")
        print(df[["orgao", "estado", "vagas", "salario", "nivel", "data_limite"]].head(20).to_string(index=False))
    else:
        print("Nenhum dado coletado.")

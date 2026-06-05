"""
Scraper para PCI Concursos - Região Sul (SC, PR, RS)
Gera UMA LINHA POR CARGO visitando cada edital individual.
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
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def _get(url: str) -> requests.Response | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        r.encoding = "utf-8"
        return r
    except requests.RequestException as e:
        log.warning(f"Erro GET {url}: {e}")
        return None


def _extrair_salario_max(texto: str) -> float | None:
    valores = re.findall(r"R\$\s*([\d\.]+,\d{2})", texto)
    resultados = []
    for v in valores:
        try:
            resultados.append(float(v.replace(".", "").replace(",", ".")))
        except ValueError:
            pass
    return max(resultados) if resultados else None


def _detectar_nivel(texto: str, cargo: str = "") -> str:
    t = texto.lower()
    c = cargo.lower()
    partes = []

    if any(p in t for p in ["superior", "graduação", "tecnólogo", "tecnol"]):
        partes.append("Superior")

    # Nível Técnico: cargo começa com "técnico" OU texto menciona "curso técnico" / "nível técnico"
    cargo_tecnico = re.match(r"^técnico\b|^tecnico\b", c)
    texto_tecnico = any(p in t for p in ["curso técnico", "nível técnico", "ensino técnico"])
    if cargo_tecnico or texto_tecnico:
        partes.append("Técnico")
    elif any(p in t for p in ["médio", "medio", "ensino médio"]):
        partes.append("Médio")

    if "fundamental" in t:
        partes.append("Fundamental")

    return " / ".join(partes) if partes else "Não informado"


def _extrair_cidade(orgao: str) -> str:
    padroes = [
        r"(?:de|do|da)\s+([A-ZÁÉÍÓÚÂÊÎÔÛÃÕÀÇ][a-záéíóúâêîôûãõàç]+(?:\s+[A-ZÁÉÍÓÚÂÊÎÔÛÃÕÀÇ][a-záéíóúâêîôûãõàç]+)*)\s*[-–,/]",
        r"(?:de|do|da)\s+([A-ZÁÉÍÓÚÂÊÎÔÛÃÕÀÇ][a-záéíóúâêîôûãõàç]+(?:\s+[A-ZÁÉÍÓÚÂÊÎÔÛÃÕÀÇ][a-záéíóúâêîôûãõàç]+)*)$",
    ]
    ignorar = {"Saúde", "Educação", "Paraná", "Santa", "Catarina", "Rio", "Grande",
               "Sul", "Brasil", "Norte", "Oeste", "Leste", "Centro", "Municipal",
               "Federal", "Estadual", "Nacional", "Regional", "Pública", "Serviço"}
    for p in padroes:
        m = re.search(p, orgao)
        if m:
            cidade = m.group(1).strip()
            if cidade not in ignorar and len(cidade) > 2:
                return cidade
    return "Não informado"


AREAS = {
    "TI / Tecnologia":     ["tecnologia", "informação", "ti ", "t.i", "sistemas", "analista de sistema",
                            "desenvolvedor", "programador", "infraestrutura", "redes", "suporte técnico",
                            "banco de dados", "segurança da informação", "ciência da computação"],
    "Saúde":               ["médico", "enfermeiro", "enfermagem", "farmacêutico", "farmácia", "odontólogo",
                            "dentista", "fisioterapeuta", "psicólogo", "nutricionista", "biomédico",
                            "fonoaudiólogo", "radiologista", "veterinário", "agente de saúde"],
    "Educação":            ["professor", "pedagogo", "docente", "educação", "escola", "ensino",
                            "magistério", "diretor escolar", "orientador educacional"],
    "Jurídico":            ["advogado", "procurador", "defensor", "jurídico", "assessor jurídico",
                            "analista jurídico", "direito"],
    "Administrativo":      ["administrativo", "assistente administrativo", "secretário", "recepcionista",
                            "auxiliar administrativo", "agente administrativo", "escriturário"],
    "Fiscal / Tributário": ["fiscal", "auditor", "tributário", "receita", "fazenda", "tributo"],
    "Engenharia":          ["engenheiro", "engenharia", "arquiteto", "arquitetura", "agrônomo", "agronomia"],
    "Segurança Pública":   ["guarda municipal", "policial", "agente de segurança", "bombeiro",
                            "agente penitenciário", "socioeducativo"],
    "Contabilidade":       ["contador", "contabilidade", "contábil", "analista contábil"],
    "Outros":              [],
}


def _detectar_area(cargo: str) -> str:
    t = cargo.lower()
    for area, palavras in AREAS.items():
        if area == "Outros":
            continue
        if any(p in t for p in palavras):
            return area
    return "Outros"


# ── Extração de cargos da página individual ───────────────────────────────────

def _extrair_cargos_pagina(html_text: str, salario_edital: float | None) -> list[dict]:
    """
    Extrai lista de cargos do texto de um edital individual.
    Retorna lista de dicts: {cargo, vagas, salario, nivel}
    """
    soup = BeautifulSoup(html_text, "html.parser")
    artigo = soup.select_one("article, .post-content, .entry-content, main") or soup
    texto = artigo.get_text(" ", strip=True)

    # Localiza seção da lista de cargos
    match_inicio = re.search(
        r"(?:cargos\s+de\s*:|vagas?\s+(?:são\s+)?para\s*:)",
        texto, re.IGNORECASE
    )
    if not match_inicio:
        return []

    secao = texto[match_inicio.end():]

    # Corta no fim da lista (primeira frase longa que não é cargo)
    fim = re.search(
        r"\b(?:A jornada|As inscrições|O concurso|Mais informa|As taxas|A seleção|"
        r"Haverá|Poderão|O prazo|O regime|O certame|Prefer)",
        secao, re.IGNORECASE
    )
    if fim:
        secao = secao[: fim.start()]

    # Extrai pares: "Nome do Cargo (N vagas)" ou "Nome do Cargo (CR)"
    cargos_raw = re.findall(
        r"([A-ZÁÉÍÓÚÂÊÎÔÛÃÕÀÇ\w][^(]{2,80}?)\s*\(([^)]{1,120})\)",
        secao
    )

    # Tenta encontrar salários individuais por cargo no texto completo
    salarios_por_cargo: dict[str, float] = {}
    for m in re.finditer(
        r"Para\s+(.{3,80}?)[,\.].{0,300}?R\$\s*([\d\.]+,\d{2})",
        texto, re.IGNORECASE | re.DOTALL
    ):
        nome = m.group(1).strip().lower()
        try:
            val = float(m.group(2).replace(".", "").replace(",", "."))
            salarios_por_cargo[nome] = val
        except ValueError:
            pass

    resultado = []
    for nome_raw, detalhe in cargos_raw:
        nome = nome_raw.strip()
        # Ignora entradas curtas ou que parecem frases
        if len(nome) < 3 or nome.lower().startswith(("a ", "as ", "o ", "os ")):
            continue

        # Vagas
        m_vagas = re.search(r"(\d+)\s*vaga", detalhe, re.IGNORECASE)
        vagas = int(m_vagas.group(1)) if m_vagas else None

        # Salário: apenas quando explicitamente mencionado para este cargo
        salario = salarios_por_cargo.get(nome.lower()) or None

        # Nível
        nivel = _detectar_nivel(detalhe + " " + nome, cargo=nome)

        resultado.append({
            "cargo": nome,
            "vagas": vagas,
            "salario": salario,
            "nivel": nivel,
        })

    return resultado


# ── Paginação ─────────────────────────────────────────────────────────────────

def _paginas_sul() -> list[str]:
    base = "https://www.pciconcursos.com.br/concursos/sul/"
    urls = [base]
    r = _get(base)
    if not r:
        return urls
    soup = BeautifulSoup(r.text, "html.parser")
    paginas = set()
    for a in soup.select("a[href*='/concursos/sul/pagina']"):
        m = re.search(r"pagina(\d+)", a["href"])
        if m:
            paginas.add(int(m.group(1)))
    for n in sorted(paginas):
        urls.append(f"{base}pagina{n}/")
    return urls


# ── Scraping principal ────────────────────────────────────────────────────────

def raspar_pagina(url: str) -> list[dict]:
    r = _get(url)
    if not r:
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    items = soup.select("div.ca")
    log.info(f"{url} → {len(items)} editais")

    linhas = []
    for idx, item in enumerate(items):
        try:
            link_tag = item.select_one("a[href]")
            orgao = link_tag.get_text(strip=True) if link_tag else "Não informado"
            link = link_tag["href"] if link_tag else ""
            if link and not link.startswith("http"):
                link = "https://www.pciconcursos.com.br" + link

            estado = item.select_one(".cc")
            estado = estado.get_text(strip=True) if estado else "Não informado"

            cd = item.select_one(".cd")
            cd_texto = cd.get_text(" ", strip=True) if cd else ""
            salario_edital = _extrair_salario_max(cd_texto)

            ce = item.select_one(".ce")
            data_limite = None
            if ce:
                m = re.search(r"(\d{2}/\d{2}/\d{4})", ce.get_text())
                if m:
                    try:
                        data_limite = datetime.strptime(m.group(1), "%d/%m/%Y").date().isoformat()
                    except ValueError:
                        pass

            cidade = _extrair_cidade(orgao)
            coletado_em = datetime.now().isoformat()

            # Visita página individual para extrair cargos
            log.info(f"  [{idx+1}/{len(items)}] {orgao}")
            r_edital = _get(link)
            cargos = []
            if r_edital:
                cargos = _extrair_cargos_pagina(r_edital.text, salario_edital)
            time.sleep(0.8)

            if cargos:
                for c in cargos:
                    linhas.append({
                        "orgao": orgao,
                        "estado": estado,
                        "cidade": cidade,
                        "cargo": c["cargo"],
                        "vagas": c["vagas"],
                        "salario": c["salario"],
                        "nivel": c["nivel"],
                        "area": _detectar_area(c["cargo"]),
                        "data_limite": data_limite,
                        "link": link,
                        "coletado_em": coletado_em,
                    })
            else:
                # Fallback: mantém uma linha com info do listing
                cargo_tag = cd.select_one("span") if cd else None
                cargo_fallback = cargo_tag.get_text(" ", strip=True).split("\n")[0].strip() if cargo_tag else "Vários Cargos"
                linhas.append({
                    "orgao": orgao,
                    "estado": estado,
                    "cidade": cidade,
                    "cargo": cargo_fallback or "Vários Cargos",
                    "vagas": None,
                    "salario": salario_edital,
                    "nivel": _detectar_nivel(cd_texto, cargo=cargo_fallback or ""),
                    "area": _detectar_area(cargo_fallback or ""),
                    "data_limite": data_limite,
                    "link": link,
                    "coletado_em": coletado_em,
                })
        except Exception as e:
            log.warning(f"Erro ao processar item: {e}")

    return linhas


def coletar_todos() -> pd.DataFrame:
    urls = _paginas_sul()
    log.info(f"Paginas encontradas: {len(urls)}")

    todos = []
    for url in urls:
        todos.extend(raspar_pagina(url))
        time.sleep(1.5)

    if not todos:
        log.warning("Nenhum concurso encontrado.")
        return pd.DataFrame()

    df = pd.DataFrame(todos)
    df.drop_duplicates(subset=["link", "cargo"], inplace=True)
    log.info(f"Total de linhas (cargos): {len(df)}")
    return df


if __name__ == "__main__":
    df = coletar_todos()
    if not df.empty:
        salvar_concursos(df)
        print(f"\nOK: {len(df)} cargos salvos no banco.")
        print(df[["orgao", "cargo", "vagas", "salario", "nivel"]].head(30).to_string(index=False))
    else:
        print("Nenhum dado coletado.")

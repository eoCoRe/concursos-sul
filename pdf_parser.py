"""
Parser de PDFs de editais de concurso.
Extrai a seção de cargos/salários do PDF e manda para o Groq.
"""

import re
import io
import logging
import requests
import pdfplumber
from bs4 import BeautifulSoup
from ai_parser import extrair_cargos_com_ia

log = logging.getLogger(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# Marcadores que indicam início da seção de cargos/salários no PDF
_MARCADORES = [
    r"cargo", r"vencimento", r"remunera", r"sal[aá]rio",
    r"quadro\s+de\s+vaga", r"tabela\s+de\s+cargo",
]
_RE_MARCADOR = re.compile("|".join(_MARCADORES), re.IGNORECASE)
_RE_VALOR    = re.compile(r"R\$\s*[\d\.]+,\d{2}")


def _buscar_links_pdf(url_artigo: str) -> list[str]:
    """Extrai links de PDF do artigo do PCI Concursos."""
    try:
        r = requests.get(url_artigo, headers=HEADERS, timeout=15)
        r.encoding = "utf-8"
        soup = BeautifulSoup(r.text, "html.parser")
        pdfs = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "arq.pciconcursos.com.br" in href and href.endswith(".pdf"):
                nome = href.lower()
                if not any(k in nome for k in ["retifica", "suspens", "erratum"]):
                    pdfs.insert(0, href)
                else:
                    pdfs.append(href)
        return pdfs
    except Exception as e:
        log.warning(f"Erro ao buscar PDFs em {url_artigo}: {e}")
        return []


def _extrair_secao_relevante(texto_completo: str, janela: int = 4000) -> str:
    """
    Em vez de pegar os primeiros N chars, encontra a seção do PDF
    que contém a tabela de cargos e salários.
    Estratégia: busca a primeira ocorrência de R$ e retorna
    um bloco de `janela` chars centrado nessa região.
    """
    # Primeiro R$ no texto
    m = _RE_VALOR.search(texto_completo)
    if m:
        # Pega contexto antes (para incluir nomes dos cargos) e depois
        inicio = max(0, m.start() - 2000)
        fim = min(len(texto_completo), inicio + janela)
        return texto_completo[inicio:fim]

    # Se não achar R$, retorna o começo (pode ter cargos sem salário declarado)
    return texto_completo[:janela]


def _extrair_texto_pdf(url_pdf: str, max_paginas: int = 15) -> str:
    """Baixa o PDF e extrai texto das primeiras N páginas."""
    try:
        r = requests.get(url_pdf, headers=HEADERS, timeout=30)
        r.raise_for_status()
        partes = []
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            for page in pdf.pages[:max_paginas]:
                # Tabelas estruturadas primeiro
                tabelas = page.extract_tables()
                if tabelas:
                    for tabela in tabelas:
                        for linha in tabela:
                            if linha:
                                partes.append(" | ".join(
                                    str(c).strip() if c else "" for c in linha
                                ))
                texto = page.extract_text()
                if texto:
                    partes.append(texto)
        return "\n".join(partes)
    except Exception as e:
        log.warning(f"Erro ao processar PDF {url_pdf}: {e}")
        return ""


def extrair_cargos_do_pdf(url_artigo: str) -> list[dict]:
    """
    Pipeline: artigo → PDF → seção relevante → IA → cargos com salário.
    """
    pdfs = _buscar_links_pdf(url_artigo)
    if not pdfs:
        return []

    log.info(f"  {len(pdfs)} PDF(s), processando principal...")

    for url_pdf in pdfs[:2]:
        texto_completo = _extrair_texto_pdf(url_pdf)
        if not texto_completo or len(texto_completo) < 200:
            continue

        secao = _extrair_secao_relevante(texto_completo)
        log.info(f"  PDF: {len(texto_completo)} chars total, enviando {len(secao)} chars (seção relevante)")

        cargos = extrair_cargos_com_ia(secao)
        if cargos:
            return cargos

    return []

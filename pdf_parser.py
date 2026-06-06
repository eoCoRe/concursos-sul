"""
Parser de PDFs de editais de concurso.
Baixa o PDF do edital, extrai o texto e manda para o Groq extrair a tabela de cargos/salários.
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


def _buscar_links_pdf(url_artigo: str) -> list[str]:
    """Extrai links de PDF do artigo do PCI Concursos."""
    try:
        r = requests.get(url_artigo, headers=HEADERS, timeout=15)
        r.encoding = "utf-8"
        soup = BeautifulSoup(r.text, "html.parser")
        pdfs = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            # PDFs hospedados no CDN do PCI (editais reais, não retificações)
            if "arq.pciconcursos.com.br" in href and href.endswith(".pdf"):
                nome = href.lower()
                # Prioriza edital principal, descarta retificações e suspensões
                if not any(k in nome for k in ["retifica", "suspens", "erratum"]):
                    pdfs.insert(0, href)
                else:
                    pdfs.append(href)
        return pdfs
    except Exception as e:
        log.warning(f"Erro ao buscar PDFs em {url_artigo}: {e}")
        return []


def _extrair_texto_pdf(url_pdf: str, max_paginas: int = 8) -> str:
    """Baixa o PDF e extrai texto das primeiras N páginas."""
    try:
        r = requests.get(url_pdf, headers=HEADERS, timeout=30)
        r.raise_for_status()
        texto_pages = []
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            for i, page in enumerate(pdf.pages[:max_paginas]):
                # Tenta extrair tabelas primeiro (mais estruturado)
                tabelas = page.extract_tables()
                if tabelas:
                    for tabela in tabelas:
                        for linha in tabela:
                            if linha:
                                texto_pages.append(" | ".join(
                                    str(c).strip() if c else "" for c in linha
                                ))
                # Depois texto normal
                texto = page.extract_text()
                if texto:
                    texto_pages.append(texto)
        return "\n".join(texto_pages)
    except Exception as e:
        log.warning(f"Erro ao processar PDF {url_pdf}: {e}")
        return ""


def extrair_cargos_do_pdf(url_artigo: str) -> list[dict]:
    """
    Pipeline completo: artigo → PDF → texto → IA → cargos com salário.
    Retorna [] se não encontrar PDF ou se a IA não extrair nada.
    """
    pdfs = _buscar_links_pdf(url_artigo)
    if not pdfs:
        log.info(f"Nenhum PDF encontrado em {url_artigo[-60:]}")
        return []

    log.info(f"  {len(pdfs)} PDF(s) encontrado(s), processando o principal...")

    # Tenta o primeiro PDF (edital principal)
    for url_pdf in pdfs[:2]:
        texto = _extrair_texto_pdf(url_pdf)
        if not texto or len(texto) < 200:
            continue

        log.info(f"  PDF extraído: {len(texto)} chars")
        cargos = extrair_cargos_com_ia(texto)
        if cargos:
            return cargos

    return []

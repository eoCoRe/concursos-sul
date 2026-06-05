"""
Parser de editais com IA (Groq/Llama).
Extrai tabela de cargos com salário real de cada edital.
"""

import os
import re
import json
import logging
import requests
from bs4 import BeautifulSoup
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

_client = None

def _groq() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    return _client


PROMPT = """Você é um extrator de dados de editais de concurso público brasileiro.

Leia o texto abaixo e retorne um JSON com a lista de cargos do edital.
Retorne APENAS o JSON, sem explicações, sem markdown, sem blocos de código.

Formato obrigatório:
[
  {{"cargo": "Nome do Cargo", "vagas": 5, "salario": 3500.00, "nivel": "Superior"}},
  {{"cargo": "Outro Cargo", "vagas": null, "salario": 1800.50, "nivel": "Médio"}}
]

Regras:
- "vagas": número inteiro quando declarado, null se for apenas Cadastro de Reserva (CR)
- "salario": valor em reais como número decimal. Se houver faixa, use o valor base/inicial. null se não declarado.
- "nivel": um de: "Superior", "Técnico", "Médio", "Fundamental", "Não informado"
- Inclua TODOS os cargos encontrados, mesmo os de cadastro de reserva
- Se não encontrar nenhum cargo, retorne []

Texto do edital:
"""


def extrair_cargos_com_ia(texto_edital: str) -> list[dict]:
    """
    Manda o texto do edital pro Groq e retorna lista de cargos com salário.
    Retorna [] se falhar ou não encontrar cargos.
    """
    if not texto_edital or len(texto_edital) < 100:
        return []

    # 1500 chars ≈ 450 tokens input — cabe bem no limite de 6000 TPM
    texto = texto_edital[:1500]

    try:
        resp = _groq().chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": PROMPT + texto}],
            temperature=0.0,
            max_tokens=1500,
        )
        raw = resp.choices[0].message.content.strip()

        # Remove blocos markdown se vier
        raw = raw.replace("```json", "").replace("```", "").strip()

        # Extrai só o array JSON
        inicio = raw.find("[")
        fim = raw.rfind("]")
        if inicio == -1 or fim == -1:
            return []
        raw = raw[inicio:fim+1]

        # Corrige escapes unicode inválidos que o Llama às vezes gera
        raw = re.sub(r'\\u[0-9a-fA-F]{0,3}(?![0-9a-fA-F])', '', raw)

        cargos = json.loads(raw)
        if not isinstance(cargos, list):
            return []

        resultado = []
        for c in cargos:
            if not isinstance(c, dict) or not c.get("cargo"):
                continue
            resultado.append({
                "cargo":   str(c.get("cargo", "")).strip(),
                "vagas":   int(c["vagas"]) if c.get("vagas") is not None else None,
                "salario": float(c["salario"]) if c.get("salario") is not None else None,
                "nivel":   str(c.get("nivel", "Não informado")).strip(),
            })
        return resultado

    except (json.JSONDecodeError, KeyError, ValueError) as e:
        log.warning(f"IA retornou JSON inválido: {e}")
        return []
    except Exception as e:
        log.warning(f"Erro na chamada Groq: {e}")
        return []


def buscar_texto_edital(url: str) -> str:
    """Baixa a página do edital e extrai o texto do artigo."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.encoding = "utf-8"
        soup = BeautifulSoup(r.text, "html.parser")
        artigo = soup.select_one("article, .post-content, .entry-content, main") or soup
        return artigo.get_text(" ", strip=True)
    except Exception as e:
        log.warning(f"Erro ao buscar {url}: {e}")
        return ""

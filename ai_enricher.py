"""
Enriquecimento com IA — roda após o scraping básico.
Para cada edital no banco, chama o Groq e atualiza cargo/vagas/salário.
"""

import sqlite3
import logging
import time
from pathlib import Path
from ai_parser import extrair_cargos_com_ia, buscar_texto_edital
from scraper import _detectar_area, _detectar_nivel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "concursos.db"


def enriquecer(max_editais: int = 999, callback=None):
    """
    Lê links únicos do banco, chama IA para cada um e substitui as linhas
    com os cargos extraídos com salário real.
    callback(atual, total, orgao) → para mostrar progresso no Streamlit.
    """
    con = sqlite3.connect(DB_PATH)

    # Pega editais únicos que ainda não foram enriquecidos (salario IS NULL na maioria)
    links = con.execute("""
        SELECT DISTINCT link, orgao, estado, cidade, salario_ref, data_limite, coletado_em
        FROM concursos
        ORDER BY data_limite ASC
        LIMIT ?
    """, (max_editais,)).fetchall()
    con.close()

    total = len(links)
    log.info(f"Enriquecendo {total} editais com IA...")

    processados = 0
    for i, (link, orgao, estado, cidade, salario_ref, data_limite, coletado_em) in enumerate(links):
        if callback:
            callback(i + 1, total, orgao)

        texto = buscar_texto_edital(link)
        cargos_ia = extrair_cargos_com_ia(texto) if texto else []

        if not cargos_ia:
            log.info(f"  [{i+1}/{total}] {orgao[:50]} — IA sem resultado, mantém dados atuais")
            time.sleep(0.3)
            continue

        con = sqlite3.connect(DB_PATH)
        # Remove linhas antigas deste edital
        con.execute("DELETE FROM concursos WHERE link = ?", (link,))

        # Insere novas linhas com dados da IA
        for c in cargos_ia:
            try:
                con.execute("""
                    INSERT OR IGNORE INTO concursos
                        (orgao, estado, cidade, cargo, vagas, salario, salario_ref,
                         nivel, area, data_limite, link, coletado_em)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    orgao, estado, cidade,
                    c["cargo"], c["vagas"], c["salario"], salario_ref,
                    c["nivel"], _detectar_area(c["cargo"]),
                    data_limite, link, coletado_em,
                ))
            except sqlite3.Error as e:
                log.warning(f"Erro ao inserir: {e}")
        con.commit()
        con.close()

        processados += 1
        log.info(f"  [{i+1}/{total}] {orgao[:50]} — {len(cargos_ia)} cargos com IA")
        time.sleep(1.5)  # respeita 6000 TPM do free tier

    log.info(f"Enriquecimento concluído: {processados}/{total} editais atualizados pela IA")
    return processados


if __name__ == "__main__":
    enriquecer()

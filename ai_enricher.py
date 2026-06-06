"""
Enriquecimento incremental com IA.
Processa APENAS editais com ia_ok = 0. Nunca reprocessa o que já foi feito.
Fonte primária: PDF do edital (salário real por cargo).
Fallback: texto do artigo.
"""

import logging
import time
from pdf_parser import extrair_cargos_do_pdf
from ai_parser import extrair_cargos_com_ia, buscar_texto_edital
from database import links_pendentes_ia, substituir_cargos_edital, marcar_ia_ok

_LIMITE_DIARIO_ESGOTADO = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def enriquecer(callback=None) -> int:
    """
    Processa todos os editais pendentes (ia_ok = 0).
    1º tenta PDF → 2º fallback para texto do artigo.
    Cada edital é processado uma vez e marcado ia_ok = 1.
    """
    pendentes = links_pendentes_ia()
    total = len(pendentes)

    if total == 0:
        log.info("Nenhum edital pendente.")
        return 0

    log.info(f"Enriquecendo {total} editais com IA (PDF → artigo)...")
    processados = 0

    global _LIMITE_DIARIO_ESGOTADO
    _LIMITE_DIARIO_ESGOTADO = False

    for i, (link, orgao, estado, cidade, salario_ref, data_limite, coletado_em) in enumerate(pendentes):
        if _LIMITE_DIARIO_ESGOTADO:
            log.error("Limite diário do Groq atingido. Parando.")
            break

        if callback:
            callback(i + 1, total, orgao)

        try:
            # 1. Tenta PDF (fonte mais confiável)
            cargos_ia = extrair_cargos_do_pdf(link)
            fonte = "PDF"

            # 2. Fallback para texto do artigo
            if not cargos_ia:
                texto = buscar_texto_edital(link)
                cargos_ia = extrair_cargos_com_ia(texto) if texto else []
                fonte = "artigo"
        except RuntimeError as e:
            if "GROQ_DAILY_LIMIT" in str(e):
                _LIMITE_DIARIO_ESGOTADO = True
                continue
            cargos_ia = []
            fonte = "erro"

        if cargos_ia:
            substituir_cargos_edital(
                link=link, cargos=cargos_ia,
                orgao=orgao, estado=estado, cidade=cidade,
                salario_ref=salario_ref, data_limite=data_limite,
                coletado_em=coletado_em,
            )
            com_sal = sum(1 for c in cargos_ia if c.get("salario"))
            log.info(f"  [{i+1}/{total}] {orgao[:45]} — {len(cargos_ia)} cargos ({com_sal} com salário) via {fonte}")
        else:
            marcar_ia_ok(link)
            log.info(f"  [{i+1}/{total}] {orgao[:45]} — sem resultado")

        processados += 1
        time.sleep(1.2)

    log.info(f"Concluído: {processados} editais processados.")
    return processados


if __name__ == "__main__":
    enriquecer()

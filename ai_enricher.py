"""
Enriquecimento incremental com IA.
Processa APENAS editais com ia_ok = 0. Nunca reprocessa o que já foi feito.
"""

import logging
import time
from ai_parser import extrair_cargos_com_ia, buscar_texto_edital
from database import links_pendentes_ia, substituir_cargos_edital, marcar_ia_ok

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def enriquecer(callback=None) -> int:
    """
    Processa todos os editais pendentes (ia_ok = 0).
    Cada edital é processado uma única vez e marcado como ia_ok = 1.
    callback(atual, total, orgao) → progresso para o Streamlit.
    """
    pendentes = links_pendentes_ia()
    total = len(pendentes)

    if total == 0:
        log.info("Nenhum edital pendente — tudo já enriquecido.")
        return 0

    log.info(f"Enriquecendo {total} editais novos com IA...")
    processados = 0

    for i, (link, orgao, estado, cidade, salario_ref, data_limite, coletado_em) in enumerate(pendentes):
        if callback:
            callback(i + 1, total, orgao)

        texto = buscar_texto_edital(link)
        cargos_ia = extrair_cargos_com_ia(texto) if texto else []

        if cargos_ia:
            substituir_cargos_edital(
                link=link, cargos=cargos_ia,
                orgao=orgao, estado=estado, cidade=cidade,
                salario_ref=salario_ref, data_limite=data_limite,
                coletado_em=coletado_em,
            )
            log.info(f"  [{i+1}/{total}] {orgao[:50]} — {len(cargos_ia)} cargos")
        else:
            # IA não encontrou nada, mas marca como processado para não tentar de novo
            marcar_ia_ok(link)
            log.info(f"  [{i+1}/{total}] {orgao[:50]} — sem resultado (marcado ok)")

        processados += 1
        time.sleep(1.5)  # respeita 6000 TPM do Groq free tier

    log.info(f"Concluído: {processados} editais processados.")
    return processados


if __name__ == "__main__":
    enriquecer()

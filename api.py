"""
API REST — Concursos Públicos Região Sul
Rodar: uvicorn api:app --reload --port 8000
Docs:  http://localhost:8000/docs
"""

from fastapi import FastAPI, Query, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import sqlite3
import pandas as pd
from pathlib import Path
from datetime import date, datetime

DB_PATH = Path(__file__).parent / "concursos.db"

app = FastAPI(
    title="Concursos Sul API",
    description="API de concursos públicos abertos na Região Sul do Brasil",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _con():
    return sqlite3.connect(DB_PATH)


def _dias_restantes(data_limite: str | None) -> int | None:
    if not data_limite:
        return None
    try:
        return (date.fromisoformat(data_limite) - date.today()).days
    except ValueError:
        return None


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["dias_restantes"] = _dias_restantes(d.get("data_limite"))
    return d


# ── GET /concursos ────────────────────────────────────────────────────────────

@app.get("/concursos", summary="Listar concursos com filtros")
def listar_concursos(
    estado:        list[str] = Query(default=[], description="SC, PR, RS"),
    cidade:        list[str] = Query(default=[]),
    area:          list[str] = Query(default=[]),
    nivel:         list[str] = Query(default=[]),
    salario_min:   Optional[float] = Query(default=None),
    salario_max:   Optional[float] = Query(default=None),
    dias_max:      Optional[int]   = Query(default=None, description="Fechar em até N dias"),
    cargo_busca:   Optional[str]   = Query(default=None, description="Texto livre no nome do cargo"),
    apenas_vagas:  bool = Query(default=False, description="Só cargos com vagas informadas"),
    page:          int  = Query(default=1, ge=1),
    page_size:     int  = Query(default=50, ge=1, le=200),
):
    query = "SELECT * FROM concursos WHERE 1=1"
    params: list = []

    if estado:
        query += f" AND estado IN ({','.join('?'*len(estado))})"
        params.extend(estado)
    if cidade:
        query += f" AND cidade IN ({','.join('?'*len(cidade))})"
        params.extend(cidade)
    if area:
        query += f" AND area IN ({','.join('?'*len(area))})"
        params.extend(area)
    if nivel:
        query += f" AND nivel IN ({','.join('?'*len(nivel))})"
        params.extend(nivel)
    if salario_min is not None:
        query += " AND salario >= ?"
        params.append(salario_min)
    if salario_max is not None:
        query += " AND salario <= ?"
        params.append(salario_max)
    if cargo_busca:
        query += " AND cargo LIKE ?"
        params.append(f"%{cargo_busca}%")
    if apenas_vagas:
        query += " AND vagas IS NOT NULL AND vagas > 0"
    if dias_max is not None:
        cutoff = date.today().isoformat()
        query += " AND data_limite >= ?"
        params.append(cutoff)

    # Total sem paginação
    con = _con()
    con.row_factory = sqlite3.Row
    total = con.execute(
        query.replace("SELECT *", "SELECT COUNT(*)"), params
    ).fetchone()[0]

    # Com ordenação e paginação
    query += " ORDER BY salario DESC NULLS LAST, data_limite ASC"
    query += f" LIMIT {page_size} OFFSET {(page - 1) * page_size}"

    rows = con.execute(query, params).fetchall()
    con.close()

    items = [_row_to_dict(r) for r in rows]

    # Filtra dias_max em memória (calculado em runtime)
    if dias_max is not None:
        items = [i for i in items if i["dias_restantes"] is None or i["dias_restantes"] <= dias_max]

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
        "data": items,
    }


# ── GET /concursos/{id} ───────────────────────────────────────────────────────

@app.get("/concursos/{id}", summary="Detalhe de um cargo")
def detalhe_concurso(id: int):
    con = _con()
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT * FROM concursos WHERE id = ?", (id,)).fetchone()
    con.close()
    if not row:
        raise HTTPException(status_code=404, detail="Concurso não encontrado")
    return _row_to_dict(row)


# ── GET /stats ────────────────────────────────────────────────────────────────

@app.get("/stats", summary="Métricas gerais")
def stats():
    con = _con()
    total       = con.execute("SELECT COUNT(*) FROM concursos").fetchone()[0]
    com_salario = con.execute("SELECT COUNT(*) FROM concursos WHERE salario IS NOT NULL").fetchone()[0]
    total_vagas = con.execute("SELECT SUM(vagas) FROM concursos WHERE vagas IS NOT NULL").fetchone()[0] or 0
    pendentes   = con.execute("SELECT COUNT(DISTINCT link) FROM concursos WHERE ia_ok=0").fetchone()[0]
    maior_sal   = con.execute("SELECT MAX(salario) FROM concursos").fetchone()[0]

    por_estado = dict(con.execute(
        "SELECT estado, COUNT(*) FROM concursos GROUP BY estado ORDER BY COUNT(*) DESC"
    ).fetchall())

    por_area = dict(con.execute(
        "SELECT area, COUNT(*) FROM concursos GROUP BY area ORDER BY COUNT(*) DESC"
    ).fetchall())

    por_nivel = dict(con.execute(
        "SELECT nivel, COUNT(*) FROM concursos GROUP BY nivel ORDER BY COUNT(*) DESC"
    ).fetchall())

    urgentes = con.execute("""
        SELECT COUNT(*) FROM concursos
        WHERE data_limite BETWEEN date('now') AND date('now', '+7 days')
    """).fetchone()[0]

    con.close()

    return {
        "total_cargos":        total,
        "cargos_com_salario":  com_salario,
        "total_vagas":         int(total_vagas),
        "pendentes_ia":        pendentes,
        "maior_salario":       maior_sal,
        "encerram_em_7_dias":  urgentes,
        "por_estado":          por_estado,
        "por_area":            por_area,
        "por_nivel":           por_nivel,
        "atualizado_em":       datetime.now().isoformat(),
    }


# ── GET /filtros ──────────────────────────────────────────────────────────────

@app.get("/filtros", summary="Opções disponíveis para filtros")
def filtros():
    con = _con()
    estados = [r[0] for r in con.execute(
        "SELECT DISTINCT estado FROM concursos WHERE estado IS NOT NULL ORDER BY estado"
    ).fetchall()]
    cidades = [r[0] for r in con.execute(
        "SELECT DISTINCT cidade FROM concursos WHERE cidade NOT IN ('Não informado', '') ORDER BY cidade"
    ).fetchall()]
    areas = [r[0] for r in con.execute(
        "SELECT DISTINCT area FROM concursos WHERE area IS NOT NULL ORDER BY area"
    ).fetchall()]
    niveis = [r[0] for r in con.execute(
        "SELECT DISTINCT nivel FROM concursos WHERE nivel IS NOT NULL ORDER BY nivel"
    ).fetchall()]
    con.close()
    return {"estados": estados, "cidades": cidades, "areas": areas, "niveis": niveis}


# ── POST /coletar ─────────────────────────────────────────────────────────────

_coleta_em_andamento = False

@app.post("/coletar", summary="Dispara nova coleta + enriquecimento IA")
def coletar(background: BackgroundTasks):
    global _coleta_em_andamento
    if _coleta_em_andamento:
        return {"status": "em_andamento", "msg": "Coleta já está rodando"}

    def _run():
        global _coleta_em_andamento
        _coleta_em_andamento = True
        try:
            from scraper import coletar_todos, salvar_concursos
            from ai_enricher import enriquecer
            df = coletar_todos()
            if not df.empty:
                salvar_concursos(df)
            enriquecer()
        finally:
            _coleta_em_andamento = False

    background.add_task(_run)
    return {"status": "iniciado", "msg": "Coleta e enriquecimento iniciados em background"}


@app.get("/coletar/status", summary="Status da coleta em andamento")
def status_coleta():
    from database import total_pendentes_ia, total_no_banco
    return {
        "em_andamento":  _coleta_em_andamento,
        "total_cargos":  total_no_banco(),
        "pendentes_ia":  total_pendentes_ia(),
    }

"""
Camada de persistência — SQLite via pandas + sqlite3
"""

import sqlite3
import pandas as pd
import logging
from pathlib import Path

log = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "concursos.db"


def _conexao() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def criar_tabela():
    with _conexao() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS concursos (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                orgao       TEXT,
                estado      TEXT,
                cidade      TEXT,
                vagas       INTEGER,
                salario     REAL,
                nivel       TEXT,
                cargo       TEXT,
                area        TEXT,
                data_limite TEXT,
                link        TEXT UNIQUE,
                coletado_em TEXT
            )
            """
        )


def salvar_concursos(df: pd.DataFrame):
    """Insere novos concursos, ignora duplicatas (link é UNIQUE)."""
    criar_tabela()
    with _conexao() as con:
        for _, row in df.iterrows():
            try:
                con.execute(
                    """
                    INSERT OR IGNORE INTO concursos
                        (orgao, estado, cidade, vagas, salario, nivel, cargo, area, data_limite, link, coletado_em)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row.get("orgao"),
                        row.get("estado"),
                        row.get("cidade"),
                        row.get("vagas"),
                        row.get("salario"),
                        row.get("nivel"),
                        row.get("cargo"),
                        row.get("area"),
                        row.get("data_limite"),
                        row.get("link"),
                        row.get("coletado_em"),
                    ),
                )
            except sqlite3.Error as e:
                log.warning(f"Erro ao inserir linha: {e}")
    log.info(f"Banco atualizado: {DB_PATH}")


def listar_cidades() -> list[str]:
    """Retorna lista ordenada de cidades distintas no banco (exceto 'Não informado')."""
    criar_tabela()
    with _conexao() as con:
        cur = con.execute(
            "SELECT DISTINCT cidade FROM concursos WHERE cidade != 'Não informado' ORDER BY cidade"
        )
        return [row[0] for row in cur.fetchall()]


def carregar_concursos(
    estados: list[str] | None = None,
    cidades: list[str] | None = None,
    salario_min: float | None = None,
    niveis: list[str] | None = None,
    areas: list[str] | None = None,
    apenas_com_vagas: bool = False,
    dias_restantes_max: int | None = None,
) -> pd.DataFrame:
    """Carrega concursos do banco aplicando filtros opcionais."""
    criar_tabela()
    query = "SELECT * FROM concursos WHERE 1=1"
    params: list = []

    if estados:
        placeholders = ",".join("?" * len(estados))
        query += f" AND estado IN ({placeholders})"
        params.extend(estados)

    if cidades:
        placeholders = ",".join("?" * len(cidades))
        query += f" AND cidade IN ({placeholders})"
        params.extend(cidades)

    if salario_min is not None:
        query += " AND salario >= ?"
        params.append(salario_min)

    if niveis:
        placeholders = ",".join("?" * len(niveis))
        query += f" AND nivel IN ({placeholders})"
        params.extend(niveis)

    if areas:
        placeholders = ",".join("?" * len(areas))
        query += f" AND area IN ({placeholders})"
        params.extend(areas)

    if apenas_com_vagas:
        query += " AND vagas IS NOT NULL AND vagas > 0"

    query += " ORDER BY data_limite ASC"

    with _conexao() as con:
        df = pd.read_sql_query(query, con, params=params)

    return df


def total_no_banco() -> int:
    criar_tabela()
    with _conexao() as con:
        cur = con.execute("SELECT COUNT(*) FROM concursos")
        return cur.fetchone()[0]

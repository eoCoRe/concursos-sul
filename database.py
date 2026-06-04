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
                vagas       INTEGER,
                salario     REAL,
                nivel       TEXT,
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
                        (orgao, estado, vagas, salario, nivel, data_limite, link, coletado_em)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row.get("orgao"),
                        row.get("estado"),
                        row.get("vagas"),
                        row.get("salario"),
                        row.get("nivel"),
                        row.get("data_limite"),
                        row.get("link"),
                        row.get("coletado_em"),
                    ),
                )
            except sqlite3.Error as e:
                log.warning(f"Erro ao inserir linha: {e}")
    log.info(f"Banco atualizado: {DB_PATH}")


def carregar_concursos(
    estados: list[str] | None = None,
    salario_min: float | None = None,
    niveis: list[str] | None = None,
    apenas_com_vagas: bool = False,
) -> pd.DataFrame:
    """Carrega concursos do banco aplicando filtros opcionais."""
    criar_tabela()
    query = "SELECT * FROM concursos WHERE 1=1"
    params: list = []

    if estados:
        placeholders = ",".join("?" * len(estados))
        query += f" AND estado IN ({placeholders})"
        params.extend(estados)

    if salario_min is not None:
        query += " AND salario >= ?"
        params.append(salario_min)

    if niveis:
        placeholders = ",".join("?" * len(niveis))
        query += f" AND nivel IN ({placeholders})"
        params.extend(niveis)

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

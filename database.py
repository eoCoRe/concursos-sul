"""
Camada de persistência — SQLite via pandas + sqlite3
Schema: UMA LINHA POR CARGO, UNIQUE(link, cargo)
ia_ok = 1 significa que o Groq já extraiu salário para aquele edital — nunca reprocessa.
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
                cargo       TEXT,
                vagas       INTEGER,
                salario     REAL,
                salario_ref REAL,
                nivel       TEXT,
                area        TEXT,
                data_limite TEXT,
                link        TEXT,
                coletado_em TEXT,
                ia_ok       INTEGER DEFAULT 0,
                UNIQUE(link, cargo)
            )
            """
        )
        # Migração: adiciona ia_ok se não existir (banco antigo)
        try:
            con.execute("ALTER TABLE concursos ADD COLUMN ia_ok INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass  # já existe


def salvar_concursos(df: pd.DataFrame):
    criar_tabela()
    novos = 0
    with _conexao() as con:
        for _, row in df.iterrows():
            try:
                cur = con.execute(
                    """
                    INSERT OR IGNORE INTO concursos
                        (orgao, estado, cidade, cargo, vagas, salario, salario_ref,
                         nivel, area, data_limite, link, coletado_em, ia_ok)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                    """,
                    (
                        row.get("orgao"),   row.get("estado"),  row.get("cidade"),
                        row.get("cargo"),   row.get("vagas"),   row.get("salario"),
                        row.get("salario_ref"), row.get("nivel"), row.get("area"),
                        row.get("data_limite"), row.get("link"), row.get("coletado_em"),
                    ),
                )
                if cur.rowcount:
                    novos += 1
            except sqlite3.Error as e:
                log.warning(f"Erro ao inserir: {e}")
    log.info(f"{novos} novas linhas inseridas — {DB_PATH}")
    return novos


def links_pendentes_ia() -> list[tuple]:
    """Retorna editais únicos que ainda não foram enriquecidos pela IA."""
    criar_tabela()
    with _conexao() as con:
        return con.execute("""
            SELECT DISTINCT link, orgao, estado, cidade, salario_ref, data_limite, coletado_em
            FROM concursos
            WHERE ia_ok = 0
            ORDER BY data_limite ASC
        """).fetchall()


def marcar_ia_ok(link: str):
    """Marca todas as linhas de um edital como enriquecidas pela IA."""
    with _conexao() as con:
        con.execute("UPDATE concursos SET ia_ok = 1 WHERE link = ?", (link,))


def substituir_cargos_edital(link: str, cargos: list[dict],
                              orgao: str, estado: str, cidade: str,
                              salario_ref, data_limite: str, coletado_em: str):
    """Deleta cargos antigos do edital e insere os novos vindos da IA."""
    from scraper import _detectar_area
    with _conexao() as con:
        con.execute("DELETE FROM concursos WHERE link = ?", (link,))
        for c in cargos:
            try:
                con.execute("""
                    INSERT OR IGNORE INTO concursos
                        (orgao, estado, cidade, cargo, vagas, salario, salario_ref,
                         nivel, area, data_limite, link, coletado_em, ia_ok)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """, (
                    orgao, estado, cidade,
                    c["cargo"], c["vagas"], c["salario"], salario_ref,
                    c["nivel"], _detectar_area(c["cargo"]),
                    data_limite, link, coletado_em,
                ))
            except sqlite3.Error as e:
                log.warning(f"Erro ao inserir cargo IA: {e}")


def listar_cidades() -> list[str]:
    criar_tabela()
    with _conexao() as con:
        cur = con.execute(
            "SELECT DISTINCT cidade FROM concursos WHERE cidade != 'Não informado' ORDER BY cidade"
        )
        return [r[0] for r in cur.fetchall()]


def carregar_concursos(
    estados: list[str] | None = None,
    cidades: list[str] | None = None,
    salario_min: float | None = None,
    niveis: list[str] | None = None,
    areas: list[str] | None = None,
    apenas_com_vagas: bool = False,
) -> pd.DataFrame:
    criar_tabela()
    query = "SELECT * FROM concursos WHERE 1=1"
    params: list = []

    if estados:
        query += f" AND estado IN ({','.join('?'*len(estados))})"
        params.extend(estados)
    if cidades:
        query += f" AND cidade IN ({','.join('?'*len(cidades))})"
        params.extend(cidades)
    if salario_min is not None:
        query += " AND salario >= ?"
        params.append(salario_min)
    if niveis:
        query += f" AND nivel IN ({','.join('?'*len(niveis))})"
        params.extend(niveis)
    if areas:
        query += f" AND area IN ({','.join('?'*len(areas))})"
        params.extend(areas)
    if apenas_com_vagas:
        query += " AND vagas IS NOT NULL AND vagas > 0"

    query += " ORDER BY salario DESC NULLS LAST"

    with _conexao() as con:
        return pd.read_sql_query(query, con, params=params)


def total_no_banco() -> int:
    criar_tabela()
    with _conexao() as con:
        return con.execute("SELECT COUNT(*) FROM concursos").fetchone()[0]


def total_pendentes_ia() -> int:
    criar_tabela()
    with _conexao() as con:
        return con.execute(
            "SELECT COUNT(DISTINCT link) FROM concursos WHERE ia_ok = 0"
        ).fetchone()[0]

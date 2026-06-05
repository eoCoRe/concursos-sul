"""
Dashboard Streamlit — Concursos Públicos Região Sul
Coleta automática diária com APScheduler + enriquecimento de salários via Groq IA.
"""

import streamlit as st
import pandas as pd
from datetime import date, datetime
from database import carregar_concursos, total_no_banco, listar_cidades, total_pendentes_ia
from scraper import coletar_todos, salvar_concursos, AREAS

st.set_page_config(
    page_title="Concursos Sul",
    page_icon="📋",
    layout="wide",
)

# ── Scheduler automático (roda uma vez por dia) ───────────────────────────────
def _coleta_diaria():
    """Chamada pelo scheduler: coleta novos + enriquece com IA."""
    import logging
    log = logging.getLogger(__name__)
    log.info("Coleta diária iniciada...")
    try:
        df = coletar_todos()
        if not df.empty:
            salvar_concursos(df)
        from ai_enricher import enriquecer
        enriquecer()
        log.info("Coleta diária concluída.")
    except Exception as e:
        log.error(f"Erro na coleta diária: {e}")


@st.cache_resource
def _iniciar_scheduler():
    from apscheduler.schedulers.background import BackgroundScheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(_coleta_diaria, "interval", hours=24, id="coleta_diaria",
                      next_run_time=None)  # não roda imediatamente ao iniciar
    scheduler.start()
    return scheduler

_iniciar_scheduler()

# ──────────────────────────────────────────────────────────────────────────────

st.title("📋 Concursos Públicos — Região Sul")

TODAS_AREAS = list(AREAS.keys())

FAIXAS_SALARIO = {
    "Até R$ 3.000":         (0,      3_000),
    "R$ 3.000 – R$ 5.000":  (3_000,  5_000),
    "R$ 5.000 – R$ 8.000":  (5_000,  8_000),
    "R$ 8.000 – R$ 12.000": (8_000,  12_000),
    "Acima de R$ 12.000":   (12_000, 9_999_999),
}

# ── Sidebar: filtros ──────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filtros")

    estados_sel = st.multiselect("Estado", ["SC", "PR", "RS"], default=["SC", "PR", "RS"])

    cidades_sel = st.multiselect(
        "Cidade", listar_cidades(), default=[], placeholder="Todas as cidades"
    )

    areas_sel = st.multiselect(
        "Área", TODAS_AREAS, default=[], placeholder="Todas as áreas"
    )

    faixas_sel = st.multiselect(
        "Faixa salarial", list(FAIXAS_SALARIO.keys()), default=[], placeholder="Todas as faixas"
    )

    niveis_sel = st.multiselect(
        "Nível",
        ["Superior", "Técnico", "Médio", "Fundamental", "Não informado"],
        default=[], placeholder="Todos os níveis",
    )

    busca_cargo = st.text_input("Buscar cargo", placeholder="Ex: Analista de TI, Médico...")

    dias_restantes = st.slider("Fechar em até (dias)", 1, 180, 180)

    apenas_com_vagas = st.checkbox("Apenas com vagas informadas", value=False)

# ── Carrega e filtra dados ────────────────────────────────────────────────────
df = carregar_concursos(
    estados=estados_sel or None,
    cidades=cidades_sel or None,
    niveis=niveis_sel or None,
    areas=areas_sel or None,
    apenas_com_vagas=apenas_com_vagas,
)

hoje = date.today()
if not df.empty:
    df["data_limite_dt"] = pd.to_datetime(df["data_limite"], errors="coerce").dt.date
    df["dias_restantes"] = df["data_limite_dt"].apply(
        lambda d: (d - hoje).days if pd.notna(d) else None
    )
    df = df[df["dias_restantes"].isna() | (df["dias_restantes"] <= dias_restantes)]
    df = df[df["dias_restantes"].isna() | (df["dias_restantes"] >= 0)]

if busca_cargo and not df.empty:
    df = df[df["cargo"].str.contains(busca_cargo, case=False, na=False)]

if faixas_sel and not df.empty:
    intervalos = [FAIXAS_SALARIO[f] for f in faixas_sel]
    def _em_faixa(row):
        val = row["salario"] if pd.notna(row.get("salario")) else row.get("salario_ref")
        return any(lo <= (val or 0) < hi for lo, hi in intervalos) if val else False
    df = df[df.apply(_em_faixa, axis=1)]

if not df.empty:
    df["_ord"] = df.apply(
        lambda r: r["salario"] if pd.notna(r.get("salario")) else r.get("salario_ref"), axis=1
    )
    df = df.sort_values("_ord", ascending=False, na_position="last").drop(columns=["_ord"])

# ── Métricas ──────────────────────────────────────────────────────────────────
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total no banco", total_no_banco())
pendentes = total_pendentes_ia()
c2.metric("Pendentes IA", pendentes,
          delta="processando..." if pendentes > 0 else None,
          delta_color="off")
c3.metric("Exibindo", len(df))
c4.metric(
    "Maior salário",
    f"R$ {df['salario'].max():,.0f}".replace(",", ".")
    if not df.empty and df["salario"].notna().any() else "—",
)
c5.metric(
    "Total vagas",
    int(df["vagas"].sum()) if not df.empty and df["vagas"].notna().any() else "—",
)

st.divider()

# ── Tabela ────────────────────────────────────────────────────────────────────
if df.empty:
    if pendentes > 0:
        st.info(f"IA ainda processando {pendentes} editais — salários chegando em breve. Recarregue a página.")
    else:
        st.info("Nenhum concurso encontrado com os filtros selecionados.")
else:
    def _prazo(dias):
        if dias is None or pd.isna(dias):
            return "—"
        dias = int(dias)
        if dias <= 7:  return f"🔴 {dias}d"
        if dias <= 30: return f"🟠 {dias}d"
        return f"🟢 {dias}d"

    df_tab = pd.DataFrame({
        "Órgão":      df["orgao"],
        "UF":         df["estado"],
        "Cidade":     df["cidade"],
        "Área":       df["area"],
        "Vagas":      df["vagas"].apply(lambda v: int(v) if pd.notna(v) else None),
        "Salário":    df["salario"],          # só o que a IA extraiu
        "Nível":      df["nivel"],
        "Cargo":      df["cargo"],
        "Prazo":      df["dias_restantes"].apply(_prazo),
        "Edital":     df["link"],
    })

    st.dataframe(
        df_tab,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Salário": st.column_config.NumberColumn("Salário (R$)", format="R$ %.2f"),
            "Vagas":   st.column_config.NumberColumn("Vagas", format="%d"),
            "Edital":  st.column_config.LinkColumn("Edital", display_text="Ver edital"),
            "Prazo":   st.column_config.TextColumn("Prazo"),
        },
    )

    st.divider()

    c1, c2, c3 = st.columns(3)
    with c1:
        st.subheader("Por Estado")
        st.bar_chart(df["estado"].value_counts())
    with c2:
        st.subheader("Por Área")
        st.bar_chart(df["area"].value_counts())
    with c3:
        st.subheader("Por Nível")
        st.bar_chart(df["nivel"].value_counts())

    st.download_button(
        "Baixar CSV",
        df.to_csv(index=False, encoding="utf-8-sig"),
        "concursos_sul.csv",
        "text/csv",
    )

# ── Rodapé com última atualização ─────────────────────────────────────────────
st.caption(f"Atualização automática diária às 7h | Dados do PCI Concursos")

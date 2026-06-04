"""
Dashboard Streamlit — Concursos Públicos Região Sul
Execute com: streamlit run app.py
"""

import streamlit as st
import pandas as pd
from datetime import date
from database import carregar_concursos, total_no_banco, listar_cidades
from scraper import coletar_todos, salvar_concursos, AREAS

st.set_page_config(
    page_title="Concursos Sul",
    page_icon="📋",
    layout="wide",
)

st.title("📋 Concursos Públicos — Região Sul")

TODAS_AREAS = list(AREAS.keys())

FAIXAS_SALARIO = {
    "Até R$ 3.000":          (0,     3_000),
    "R$ 3.000 – R$ 5.000":   (3_000, 5_000),
    "R$ 5.000 – R$ 8.000":   (5_000, 8_000),
    "R$ 8.000 – R$ 12.000":  (8_000, 12_000),
    "Acima de R$ 12.000":    (12_000, 9_999_999),
}

# ── Barra lateral: filtros ────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filtros")

    estados_sel = st.multiselect(
        "Estado",
        options=["SC", "PR", "RS"],
        default=["SC", "PR", "RS"],
    )

    cidades_disponiveis = listar_cidades()
    cidades_sel = st.multiselect(
        "Cidade",
        options=cidades_disponiveis,
        default=[],
        placeholder="Todas as cidades",
    )

    areas_sel = st.multiselect(
        "Área",
        options=TODAS_AREAS,
        default=[],
        placeholder="Todas as áreas",
    )

    faixas_sel = st.multiselect(
        "Faixa salarial",
        options=list(FAIXAS_SALARIO.keys()),
        default=[],
        placeholder="Todas as faixas",
    )

    niveis_sel = st.multiselect(
        "Nível de escolaridade",
        options=["Superior", "Médio", "Fundamental", "Não informado"],
        default=[],
        placeholder="Todos os níveis",
    )

    dias_restantes = st.slider(
        "Fechar em até (dias)",
        min_value=1,
        max_value=180,
        value=180,
        help="Mostra apenas editais que fecham dentro deste prazo",
    )

    apenas_com_vagas = st.checkbox("Apenas com vagas informadas", value=False)

    st.divider()

    if st.button("Coletar agora (novo scraping)", use_container_width=True):
        with st.spinner("Raspando PCI Concursos..."):
            df_novo = coletar_todos()
            if not df_novo.empty:
                salvar_concursos(df_novo)
                st.success(f"{len(df_novo)} concursos coletados e salvos!")
                st.rerun()
            else:
                st.warning("Nenhum dado coletado. Verifique a conexão.")

# ── Carrega dados ─────────────────────────────────────────────────────────────
df = carregar_concursos(
    estados=estados_sel if estados_sel else None,
    cidades=cidades_sel if cidades_sel else None,
    niveis=niveis_sel if niveis_sel else None,
    areas=areas_sel if areas_sel else None,
    apenas_com_vagas=apenas_com_vagas,
)

# Calcula dias restantes
hoje = date.today()
if not df.empty and "data_limite" in df.columns:
    df["data_limite_dt"] = pd.to_datetime(df["data_limite"], errors="coerce").dt.date
    df["dias_restantes"] = df["data_limite_dt"].apply(
        lambda d: (d - hoje).days if pd.notna(d) else None
    )
    df = df[df["dias_restantes"].isna() | (df["dias_restantes"] <= dias_restantes)]
    df = df[df["dias_restantes"].isna() | (df["dias_restantes"] >= 0)]

# Aplica filtro de faixa salarial
if faixas_sel and not df.empty:
    intervalos = [FAIXAS_SALARIO[f] for f in faixas_sel]
    mask = df["salario"].apply(
        lambda s: any(lo <= (s or 0) < hi for lo, hi in intervalos) if pd.notna(s) else False
    )
    df = df[mask]

# Ordena por salário (maior primeiro)
if not df.empty:
    df = df.sort_values("salario", ascending=False, na_position="last")

# ── Métricas de resumo ────────────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total no banco", total_no_banco())
col2.metric("Exibindo agora", len(df))
col3.metric(
    "Maior salário (filtro)",
    f"R$ {df['salario'].max():,.0f}".replace(",", ".") if not df.empty and df["salario"].notna().any() else "—",
)
col4.metric(
    "Total de vagas (filtro)",
    int(df["vagas"].sum()) if not df.empty and df["vagas"].notna().any() else "—",
)

st.divider()

# ── Tabela principal (Excel-like, clicável nos cabeçalhos) ───────────────────
if df.empty:
    st.info("Nenhum concurso encontrado com os filtros selecionados. Clique em 'Coletar agora' para buscar dados.")
else:
    def _urgencia(dias):
        if dias is None or pd.isna(dias):
            return "—"
        dias = int(dias)
        if dias <= 7:
            return f"🔴 {dias}d"
        if dias <= 30:
            return f"🟠 {dias}d"
        return f"🟢 {dias}d"

    df_tabela = pd.DataFrame({
        "Órgão":          df["orgao"],
        "UF":             df["estado"],
        "Cidade":         df["cidade"],
        "Área":           df["area"],
        "Vagas":          df["vagas"],
        "Salário (R$)":   df["salario"],
        "Nível":          df["nivel"],
        "Cargos":         df["cargo"],
        "Prazo":          df["dias_restantes"].apply(_urgencia),
        "Edital":         df["link"],
    })

    st.dataframe(
        df_tabela,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Salário (R$)": st.column_config.NumberColumn(
                "Salário (R$)",
                format="R$ %.2f",
            ),
            "Vagas": st.column_config.NumberColumn(
                "Vagas",
                format="%d",
            ),
            "Edital": st.column_config.LinkColumn(
                "Edital",
                display_text="Ver edital",
            ),
            "Prazo": st.column_config.TextColumn("Prazo"),
        },
    )

    st.divider()

    # ── Gráficos ──────────────────────────────────────────────────────────────
    col_g1, col_g2, col_g3 = st.columns(3)

    with col_g1:
        st.subheader("Por Estado")
        st.bar_chart(df["estado"].value_counts())

    with col_g2:
        st.subheader("Por Área")
        st.bar_chart(df["area"].value_counts())

    with col_g3:
        st.subheader("Por Nível")
        st.bar_chart(df["nivel"].value_counts())

    st.download_button(
        label="Baixar CSV",
        data=df.to_csv(index=False, encoding="utf-8-sig"),
        file_name="concursos_sul.csv",
        mime="text/csv",
    )

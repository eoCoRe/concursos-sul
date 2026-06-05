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
        options=["Superior", "Técnico", "Médio", "Fundamental", "Não informado"],
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

    busca_cargo = st.text_input(
        "Buscar cargo",
        placeholder="Ex: Analista de TI, Médico...",
    )

    apenas_com_vagas = st.checkbox("Apenas com vagas informadas", value=False)

    st.divider()

    if st.button("Coletar agora (scraping)", use_container_width=True):
        with st.spinner("Raspando PCI Concursos (~2 min)..."):
            df_novo = coletar_todos()
            if not df_novo.empty:
                salvar_concursos(df_novo)
                st.success(f"{len(df_novo)} cargos coletados!")
                st.rerun()
            else:
                st.warning("Nenhum dado coletado.")

    if st.button("Enriquecer salários com IA", use_container_width=True):
        from ai_enricher import enriquecer
        progresso = st.progress(0, text="Iniciando IA...")
        resultado = {"n": 0}

        def _cb(atual, total, orgao):
            resultado["n"] = atual
            progresso.progress(atual / total, text=f"[{atual}/{total}] {orgao[:40]}...")

        processados = enriquecer(callback=_cb)
        progresso.empty()
        st.success(f"IA atualizou {processados} editais com salários reais!")
        st.rerun()
    st.caption("Coleta: ~2min | Enriquecer IA: ~5min")

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

# Aplica busca por cargo (texto livre)
if busca_cargo and not df.empty:
    df = df[df["cargo"].str.contains(busca_cargo, case=False, na=False)]

# Aplica filtro de faixa salarial (usa individual se disponível, senão ref do edital)
if faixas_sel and not df.empty:
    intervalos = [FAIXAS_SALARIO[f] for f in faixas_sel]
    def _em_faixa(row):
        val = row["salario"] if pd.notna(row.get("salario")) else row.get("salario_ref")
        if val is None or pd.isna(val):
            return False
        return any(lo <= val < hi for lo, hi in intervalos)
    df = df[df.apply(_em_faixa, axis=1)]

# Ordena por salário (usa individual se disponível, senão ref)
if not df.empty:
    df["_sal_ord"] = df.apply(
        lambda r: r["salario"] if pd.notna(r.get("salario")) else r.get("salario_ref"), axis=1
    )
    df = df.sort_values("_sal_ord", ascending=False, na_position="last").drop(columns=["_sal_ord"])

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

    def _salario_display(row):
        """Individual quando declarado, senão máximo do edital com prefixo 'até'."""
        if pd.notna(row.get("salario")):
            return row["salario"]
        return row.get("salario_ref")

    def _salario_label(row):
        """Marca com * quando é referência do edital, não individual."""
        if pd.notna(row.get("salario")):
            return ""
        return "até"

    df_tabela = pd.DataFrame({
        "Órgão":        df["orgao"],
        "UF":           df["estado"],
        "Cidade":       df["cidade"],
        "Área":         df["area"],
        "Vagas":        df["vagas"].apply(lambda v: int(v) if pd.notna(v) else None),
        "Salário":      df.apply(_salario_display, axis=1),
        "Ref":          df.apply(_salario_label, axis=1),
        "Nível":        df["nivel"],
        "Cargo":        df["cargo"],
        "Prazo":          df["dias_restantes"].apply(_urgencia),
        "Edital":         df["link"],
    })

    st.dataframe(
        df_tabela,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Salário": st.column_config.NumberColumn(
                "Salário (R$)",
                format="R$ %.2f",
            ),
            "Ref": st.column_config.TextColumn(
                "",
                help="'até' = salário máximo do edital (individual não declarado). Em branco = salário específico do cargo.",
                width="small",
            ),
            "Vagas": st.column_config.NumberColumn(
                "Vagas",
                format="%d",
                help="Vazio = Cadastro de Reserva sem número fixo",
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

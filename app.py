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

    salario_min = st.number_input(
        "Salário mínimo (R$)",
        min_value=0,
        value=0,
        step=500,
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

# ── Carrega dados com filtros ─────────────────────────────────────────────────
df = carregar_concursos(
    estados=estados_sel if estados_sel else None,
    cidades=cidades_sel if cidades_sel else None,
    salario_min=salario_min if salario_min > 0 else None,
    niveis=niveis_sel if niveis_sel else None,
    areas=areas_sel if areas_sel else None,
    apenas_com_vagas=apenas_com_vagas,
)

# Calcula dias restantes e aplica filtro de prazo
hoje = date.today()
if not df.empty and "data_limite" in df.columns:
    df["data_limite_dt"] = pd.to_datetime(df["data_limite"], errors="coerce").dt.date
    df["dias_restantes"] = df["data_limite_dt"].apply(
        lambda d: (d - hoje).days if pd.notna(d) else None
    )
    # Aplica filtro de prazo (ignora registros sem data)
    df = df[df["dias_restantes"].isna() | (df["dias_restantes"] <= dias_restantes)]
    df = df[df["dias_restantes"].isna() | (df["dias_restantes"] >= 0)]

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


def _badge_dias(dias):
    """Retorna HTML com badge colorido conforme urgência."""
    if dias is None or pd.isna(dias):
        return '<span style="color:#888">—</span>'
    dias = int(dias)
    if dias <= 7:
        cor = "#e74c3c"   # vermelho — urgente
        icone = "🔴"
    elif dias <= 30:
        cor = "#e67e22"   # laranja — atenção
        icone = "🟠"
    else:
        cor = "#27ae60"   # verde — tranquilo
        icone = "🟢"
    return (
        f'<span style="color:{cor};font-weight:bold">'
        f'{icone} {dias}d'
        f'</span>'
    )


# ── Tabela principal ──────────────────────────────────────────────────────────
if df.empty:
    st.info("Nenhum concurso encontrado com os filtros selecionados. Clique em 'Coletar agora' para buscar dados.")
else:
    df_exibir = df.copy()

    # Formata salário
    df_exibir["salario_fmt"] = df_exibir["salario"].apply(
        lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if pd.notna(x) else "—"
    )

    # Dias restantes com badge colorido
    df_exibir["prazo"] = df_exibir["dias_restantes"].apply(_badge_dias)

    # Data formatada BR
    df_exibir["data_fmt"] = df_exibir["data_limite_dt"].apply(
        lambda d: d.strftime("%d/%m/%Y") if pd.notna(d) else "—"
    )

    # Link clicável
    df_exibir["link_fmt"] = df_exibir["link"].apply(
        lambda url: f'<a href="{url}" target="_blank">Ver edital</a>' if url else "—"
    )

    colunas_html = {
        "orgao": "Órgão",
        "estado": "UF",
        "cidade": "Cidade",
        "area": "Área",
        "vagas": "Vagas",
        "salario_fmt": "Salário",
        "nivel": "Nível",
        "cargo": "Cargos",
        "data_fmt": "Encerra em",
        "prazo": "Dias Restantes",
        "link_fmt": "Edital",
    }

    tabela = df_exibir[list(colunas_html.keys())].rename(columns=colunas_html)

    st.write(tabela.to_html(escape=False, index=False), unsafe_allow_html=True)

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

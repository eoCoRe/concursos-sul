"""
Dashboard Streamlit — Concursos Públicos Região Sul
Execute com: streamlit run app.py
"""

import streamlit as st
import pandas as pd
from database import carregar_concursos, total_no_banco
from scraper import coletar_todos, salvar_concursos

st.set_page_config(
    page_title="Concursos Sul",
    page_icon="📋",
    layout="wide",
)

st.title("📋 Concursos Públicos — Região Sul")

# ── Barra lateral: filtros ────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filtros")

    estados_sel = st.multiselect(
        "Estado",
        options=["SC", "PR", "RS"],
        default=["SC", "PR"],
    )

    salario_min = st.number_input(
        "Salário mínimo (R$)",
        min_value=0,
        value=3000,
        step=500,
    )

    niveis_sel = st.multiselect(
        "Nível de escolaridade",
        options=["Superior", "Médio", "Fundamental", "Não informado"],
        default=["Superior", "Médio"],
    )

    apenas_com_vagas = st.checkbox("Apenas com vagas informadas", value=False)

    st.divider()

    if st.button("🔄 Coletar agora (novo scraping)", use_container_width=True):
        with st.spinner("Raspando PCI Concursos..."):
            df_novo = coletar_todos()
            if not df_novo.empty:
                salvar_concursos(df_novo)
                st.success(f"{len(df_novo)} concursos coletados e salvos!")
            else:
                st.warning("Nenhum dado coletado. Verifique a conexão.")

# ── Métricas de resumo ────────────────────────────────────────────────────────
df = carregar_concursos(
    estados=estados_sel if estados_sel else None,
    salario_min=salario_min if salario_min > 0 else None,
    niveis=niveis_sel if niveis_sel else None,
    apenas_com_vagas=apenas_com_vagas,
)

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

# ── Tabela principal ──────────────────────────────────────────────────────────
if df.empty:
    st.info("Nenhum concurso encontrado com os filtros selecionados. Clique em 'Coletar agora' para buscar dados.")
else:
    # Colunas amigáveis para exibição
    colunas_exibir = {
        "orgao": "Órgão",
        "estado": "Estado",
        "vagas": "Vagas",
        "salario": "Salário (R$)",
        "nivel": "Nível",
        "data_limite": "Data Limite",
        "link": "Link",
    }

    df_exibir = df[list(colunas_exibir.keys())].rename(columns=colunas_exibir)

    # Formata salário
    df_exibir["Salário (R$)"] = df_exibir["Salário (R$)"].apply(
        lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if pd.notna(x) else "—"
    )

    # Transforma link em HTML clicável
    df_exibir["Link"] = df_exibir["Link"].apply(
        lambda url: f'<a href="{url}" target="_blank">Ver edital</a>' if url else "—"
    )

    st.write(
        df_exibir.to_html(escape=False, index=False),
        unsafe_allow_html=True,
    )

    st.divider()

    # ── Gráficos ──────────────────────────────────────────────────────────────
    col_g1, col_g2 = st.columns(2)

    with col_g1:
        st.subheader("Concursos por Estado")
        contagem_estado = df["estado"].value_counts()
        st.bar_chart(contagem_estado)

    with col_g2:
        st.subheader("Distribuição por Nível")
        contagem_nivel = df["nivel"].value_counts()
        st.bar_chart(contagem_nivel)

    # Download CSV
    st.download_button(
        label="⬇️ Baixar CSV",
        data=df.to_csv(index=False, encoding="utf-8-sig"),
        file_name="concursos_sul.csv",
        mime="text/csv",
    )

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

# Configuração do banco
DB_USER = "postgres"
DB_PASS = "2025"   # 🔒 troque pela senha real do seu banco
DB_HOST = "localhost"   # ou o nome do container (ex: "db") se usar Docker Compose
DB_PORT = "5432"
DB_NAME = "pedidos_db"

# Criar conexão com o PostgreSQL
engine = create_engine(
    f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

st.title("📊 Painel de Pedidos")

try:
    # Ler dados da tabela
    query = "SELECT * FROM public.pedidos_tb;"
    df = pd.read_sql(query, engine)

    # Exibir dados
    st.subheader("📋 Tabela de Pedidos")
    st.dataframe(df)

    # Estatísticas simples
    st.subheader("📈 Resumo")
    st.write("✅ Total de pedidos:", len(df))

    if "valor" in df.columns:
        st.write("💰 Valor total:", df["valor"].sum())

except SQLAlchemyError as e:
    st.error(f"Erro ao conectar ou consultar o banco: {e}")

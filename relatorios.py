import pandas as pd
from sqlalchemy import create_engine
from datetime import date
import os

# --- Configurações de Banco ---
# Usaremos a mesma variável de ambiente do seu crud.py
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql+psycopg2://postgres:2025@localhost:5432/pedidos_db')
engine = create_engine(DATABASE_URL)

STATUS_BACKLOG = [2, 3]  # Backlog e Em Montagem
STATUS_CONCLUIDO = [4]   # Concluido

# --- Funções de Lógica (Reaproveitadas do script original) ---

def padronizar_colunas(df):
    """Padroniza os nomes das colunas de um DataFrame."""
    if "pv" in df.columns: # Já vem como 'pv' do seu CRUD
        pass
    if "quantidade" in df.columns and "qtd_maquinas" not in df.columns:
        df.rename(columns={"quantidade": "qtd_maquinas"}, inplace=True)
    return df

def buscar_pedidos_concluidos(start_date, end_date):
    """
    Busca registros concluídos dentro de um intervalo de datas,
    ajustando para o fuso horário de Brasília.
    """
    try:
        placeholders = ", ".join(map(str, STATUS_CONCLUIDO))
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        # --- MODIFICAÇÃO PRINCIPAL ---
        # Converte o timestamp da conclusão para o fuso 'America/Sao_Paulo'
        # ANTES de extrair a data. Isso garante que a data corresponda
        # ao dia correto no horário de Brasília.
        query = (
            f"SELECT * FROM pedidos_tb WHERE status_id IN ({placeholders}) "
            f"AND DATE(data_conclusao AT TIME ZONE 'America/Sao_Paulo') BETWEEN '{start_str}' AND '{end_str}'"
        )
        
        df = pd.read_sql_query(query, engine)
        return padronizar_colunas(df)
    except Exception as e:
        print(f"Erro ao buscar dados concluídos: {e}")
        return pd.DataFrame()

def buscar_pedidos_backlog():
    """Busca todos os registros que estão no backlog."""
    try:
        placeholders = ", ".join(map(str, STATUS_BACKLOG))
        query = f"SELECT * FROM pedidos_tb WHERE status_id IN ({placeholders})"
        df = pd.read_sql_query(query, engine)
        return padronizar_colunas(df)
    except Exception as e:
        print(f"Erro ao buscar dados de backlog: {e}")
        return pd.DataFrame()

def criar_texto_relatorio(start_date_str, end_date_str):
    """Função principal que gera o texto completo do relatório para ser usada pelo Flask."""
    start = date.fromisoformat(start_date_str)
    end = date.fromisoformat(end_date_str)

    df_backlog = buscar_pedidos_backlog()
    df_concluidos = buscar_pedidos_concluidos(start, end)

    atividades_realizadas = []
    atividades_backlog = []

    # Processamento de Concluídos
    if not df_concluidos.empty:
        df_concluidos["pv"] = df_concluidos["pv"].astype(str)
        teravix_df = df_concluidos[df_concluidos["pv"].str.contains("TERAVIX", na=False, case=False)]
        pv_df = df_concluidos[~df_concluidos["pv"].str.contains("TERAVIX", na=False, case=False)]
        if len(pv_df) > 0:
            atividades_realizadas.append(f"• {len(pv_df)} PV(s) com {int(pv_df['qtd_maquinas'].sum())} unidades")
        if len(teravix_df) > 0:
            atividades_realizadas.append(f"• {len(teravix_df)} OP(s) Teravix com {int(teravix_df['qtd_maquinas'].sum())} unidades")

    # Processamento de Backlog
    if not df_backlog.empty:
        df_backlog["pv"] = df_backlog["pv"].astype(str)
        teravix_back = df_backlog[df_backlog["pv"].str.contains("TERAVIX", na=False, case=False)]
        pv_back = df_backlog[~df_backlog["pv"].str.contains("TERAVIX", na=False, case=False)]
        if len(pv_back) > 0:
            atividades_backlog.append(f"• {len(pv_back)} PV(s) com {int(pv_back['qtd_maquinas'].sum())} unidades")
        if len(teravix_back) > 0:
            atividades_backlog.append(f"• {len(teravix_back)} OP(s) Teravix com {int(teravix_back['qtd_maquinas'].sum())} unidades")

    # Montagem do Texto Final
    dia_inicio = start.strftime("%d/%m")
    dia_fim = end.strftime("%d/%m")
    titulo = f"Relatório de Atividades - {dia_inicio}" if start == end else f"Relatório de Atividades - período de {dia_inicio} a {dia_fim}"
    corpo_realizadas = "Nenhuma atividade realizada no período." if not atividades_realizadas else "\n".join(atividades_realizadas)
    corpo_backlog = "Nenhuma atividade futura na fila." if not atividades_backlog else "\n".join(atividades_backlog)
    
    return (
        f"{titulo}\n\n"
        f"{corpo_realizadas}\n\n"
        f"Backlog:\n{corpo_backlog}"
    )
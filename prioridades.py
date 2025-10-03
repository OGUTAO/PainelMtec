import sys
import os
import locale
import random
import pandas as pd
import psycopg2
from datetime import datetime, timedelta
import numpy as np
import time
import traceback
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QFrame, QProgressBar, QSizePolicy, QPushButton, QGridLayout)
from PySide6.QtGui import QFont, QKeyEvent
from PySide6.QtCore import QTimer, Qt

# --- TIMEZONE / BRASÍLIA ---
TIMEZONE_NAME = "America/Sao_Paulo"
try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo(TIMEZONE_NAME)
except ImportError:
    import pytz
    TZ = pytz.timezone(TIMEZONE_NAME)

def to_brasilia(series):
    s = pd.to_datetime(series, errors='coerce')
    try:
        if s.dt.tz is None:
            s = s.dt.tz_localize('UTC').dt.tz_convert(TZ)
        else:
            s = s.dt.tz_convert(TZ)
    except Exception:
        s = pd.to_datetime(series, errors='coerce')
    return s

# --- CONFIGURAÇÃO GERAL E DE DADOS ---
SCALE_FACTOR = 0.8
META_SEMANAL = 200

# --- NOVAS CONFIGURAÇÕES DE BANCO DE DADOS POSTGRESQL ---
DB_HOST = "localhost"
DB_NAME = "pedidos_db"
DB_USER = "postgres"
DB_PASSWORD = "2025"

# --- CONSTANTES DE COLUNAS E STATUS ---
COLUNA_PEDIDO_ID, COLUNA_PV, COLUNA_SERVICO, COLUNA_STATUS, COLUNA_DATA_STATUS, COLUNA_QTD, COLUNA_EQUIPAMENTO, COLUNA_URGENTE, COLUNA_DATA_CONCLUSAO, COLUNA_IMAGEM = \
    'id', 'pv', 'descricao_servico', 'nome_status', 'data_criacao', 'quantidade', 'equipamento', 'urgente', 'data_conclusao', 'image'
    
STATUS_PENDENTE, STATUS_BACKLOG, STATUS_AGUARDANDO_CHEGADA, STATUS_EM_MONTAGEM, STATUS_CONCLUIDO, STATUS_CANCELADO, STATUS_URGENTE = \
    'Pendente', 'Backlog', 'Aguardando Chegada', 'Em Montagem', 'Concluído', 'Cancelado', 'Urgente'


# --- CONEXÃO COM O BANCO DE DADOS POSTGRESQL ---
def get_db_connection():
    """Cria e retorna uma conexão com o banco de dados PostgreSQL."""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            client_encoding='utf8'
        )
        return conn
    except psycopg2.Error as e:
        raise Exception(f"Erro ao conectar ao banco de dados: {e}")

# --- LÓGICA DE DADOS REESCRITA E CORRIGIDA ---
def carregar_dados():
    """Carrega todos os dados diretamente do banco de dados PostgreSQL."""
    print(f"Carregando dados do banco de dados: {DB_NAME}...")
    conn = None
    try:
        conn = get_db_connection()
        # CORREÇÃO 1: Adicionado p.status_id à consulta para permitir filtragem numérica
        query = f"""
            SELECT 
                p.id AS "{COLUNA_PEDIDO_ID}",
                p.status_id,
                p.equipamento AS "{COLUNA_EQUIPAMENTO}",
                p.pv AS "{COLUNA_PV}",
                p.descricao_servico AS "{COLUNA_SERVICO}",
                s.nome_status AS "{COLUNA_STATUS}",
                p.data_criacao AS "{COLUNA_DATA_STATUS}",
                p.quantidade AS "{COLUNA_QTD}",
                p.urgente AS "{COLUNA_URGENTE}",
                p.data_conclusao AS "{COLUNA_DATA_CONCLUSAO}",
                i.nome AS "{COLUNA_IMAGEM}"
            FROM 
                pedidos_tb p
            JOIN
                status_td s ON p.status_id = s.id
            LEFT JOIN                               
                imagem_td i ON p.imagem_id = i.id 
            ORDER BY
                p.urgente DESC, p.prioridade ASC;
            """
        df = pd.read_sql(query, conn)
        print("Dados brutos carregados do banco de dados:")
        print(df.head())
        
    except Exception as e:
        raise Exception(f"Não foi possível carregar os dados do banco de dados.\nErro: {e}")
    finally:
        if conn:
            conn.close()

    if df.empty:
        print("AVISO: O banco de dados não retornou nenhum pedido.")
        expected_columns = [
            COLUNA_PEDIDO_ID, COLUNA_EQUIPAMENTO, COLUNA_PV, COLUNA_SERVICO,
            COLUNA_STATUS, COLUNA_DATA_STATUS, COLUNA_QTD, COLUNA_URGENTE, COLUNA_DATA_CONCLUSAO
        ]
        empty_df = pd.DataFrame(columns=expected_columns)
        return empty_df.copy(), empty_df.copy(), empty_df.copy(), empty_df.copy(), (0,0,0,0,0,0), (0,0,0,0,0,0)

    # --- Processamento dos dados ---
    df_full = df.copy()
    
    df_full[COLUNA_DATA_STATUS] = to_brasilia(df_full[COLUNA_DATA_STATUS])
    df_full[COLUNA_DATA_CONCLUSAO] = to_brasilia(df_full[COLUNA_DATA_CONCLUSAO])
    df_full[COLUNA_STATUS] = df_full[COLUNA_STATUS].astype(str).str.strip()
    df_full.rename(columns={COLUNA_URGENTE: 'is_urgent'}, inplace=True, errors='ignore')
    
    # --- CORREÇÃO 2: Usar IDs numéricos para toda a filtragem de status ---
    STATUS_ID_CONCLUIDO = 4
    STATUS_ID_CANCELADO = 6

    hoje_obj = datetime.now(TZ)
    inicio_do_dia = hoje_obj.replace(hour=0, minute=0, second=0, microsecond=0)
    fim_do_dia = hoje_obj.replace(hour=23, minute=59, second=59, microsecond=999999)

    df_finalizados = df_full.dropna(subset=[COLUNA_DATA_CONCLUSAO]).copy()

    df_concluidos_dia = df_finalizados[
        (df_finalizados['status_id'] == STATUS_ID_CONCLUIDO) &
        (df_finalizados[COLUNA_DATA_CONCLUSAO] >= inicio_do_dia) &
        (df_finalizados[COLUNA_DATA_CONCLUSAO] <= fim_do_dia)
    ].sort_values(by=COLUNA_DATA_CONCLUSAO, ascending=False)
    
    df_cancelados_dia = df_finalizados[
        (df_finalizados['status_id'] == STATUS_ID_CANCELADO) &
        (df_finalizados[COLUNA_DATA_CONCLUSAO] >= inicio_do_dia) &
        (df_finalizados[COLUNA_DATA_CONCLUSAO] <= fim_do_dia)
    ].sort_values(by=COLUNA_DATA_CONCLUSAO, ascending=False)
    
    # DataFrame principal agora é filtrado por ID, o que é mais seguro
    status_finalizados_ids_lista = [STATUS_ID_CONCLUIDO, STATUS_ID_CANCELADO]
    df_principal = df_full[~df_full['status_id'].isin(status_finalizados_ids_lista)].copy()
    
    if not df_principal.empty:
        df_principal = df_principal.reset_index(drop=True)
        df_principal['Prioridade_Display'] = df_principal.index + 1

    # Cálculos de totais continuam funcionando, pois dependem dos DataFrames já corrigidos
    is_teravix_concluido = df_concluidos_dia[COLUNA_PV].astype(str).str.contains('TERAVIX', na=False, case=False)
    teravix_concluidos_qtd = df_concluidos_dia.loc[is_teravix_concluido, COLUNA_QTD].sum()
    pv_concluidos_qtd = df_concluidos_dia.loc[~is_teravix_concluido, COLUNA_QTD].sum()
    totais_concluidos = (len(df_concluidos_dia[is_teravix_concluido]), len(df_concluidos_dia[~is_teravix_concluido]), len(df_concluidos_dia),
                         teravix_concluidos_qtd, pv_concluidos_qtd, df_concluidos_dia[COLUNA_QTD].sum())

    is_teravix_cancelado = df_cancelados_dia[COLUNA_PV].astype(str).str.contains('TERAVIX', na=False, case=False)
    teravix_cancelados_qtd = df_cancelados_dia.loc[is_teravix_cancelado, COLUNA_QTD].sum()
    pv_cancelados_qtd = df_cancelados_dia.loc[~is_teravix_cancelado, COLUNA_QTD].sum()
    totais_cancelados = (len(df_cancelados_dia[is_teravix_cancelado]), len(df_cancelados_dia[~is_teravix_cancelado]), len(df_cancelados_dia),
                         teravix_cancelados_qtd, pv_cancelados_qtd, df_cancelados_dia[COLUNA_QTD].sum())

    return df_full, df_principal, df_concluidos_dia, df_cancelados_dia, totais_concluidos, totais_cancelados


def calcular_metricas_dashboard(df_full):
    if df_full.empty or 'status_id' not in df_full.columns:
        return {"total_mes_atual": 0, "total_mes_atual_qtd": 0, "media_diaria_atual": 0, "media_diaria_qtd": 0,
                "total_mes_anterior": 0, "media_diaria_anterior": 0,
                "recorde_dia_valor": 0, "recorde_dia_data": "N/A", "recorde_dia_qtd": 0}

    # CORREÇÃO 3: Usar ID numérico para filtrar métricas
    STATUS_ID_CONCLUIDO = 4
    
    hoje = datetime.now(TZ)
    inicio_mes_atual = hoje.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    df_concluidos_mes_atual = df_full[
        (df_full['status_id'] == STATUS_ID_CONCLUIDO) & 
        (df_full[COLUNA_DATA_CONCLUSAO] >= inicio_mes_atual) & 
        (df_full[COLUNA_DATA_CONCLUSAO] <= hoje)
    ]
    
    total_mes_atual_pedidos = len(df_concluidos_mes_atual)
    total_mes_atual_qtd = df_concluidos_mes_atual[COLUNA_QTD].sum()
    dias_uteis_mes_atual = np.busday_count(inicio_mes_atual.strftime('%Y-%m-%d'), (hoje + timedelta(days=1)).strftime('%Y-%m-%d'))
    media_diaria_atual = total_mes_atual_pedidos / dias_uteis_mes_atual if dias_uteis_mes_atual > 0 else 0
    media_diaria_qtd = total_mes_atual_qtd / dias_uteis_mes_atual if dias_uteis_mes_atual > 0 else 0
    
    fim_mes_anterior = inicio_mes_atual - timedelta(days=1); inicio_mes_anterior = fim_mes_anterior.replace(day=1)
    df_concluidos_mes_anterior = df_full[
        (df_full['status_id'] == STATUS_ID_CONCLUIDO) & 
        (df_full[COLUNA_DATA_CONCLUSAO] >= inicio_mes_anterior) & 
        (df_full[COLUNA_DATA_CONCLUSAO] <= fim_mes_anterior)
    ]
    dias_uteis_mes_anterior = np.busday_count(inicio_mes_anterior.strftime('%Y-%m-%d'), (fim_mes_anterior + timedelta(days=1)).strftime('%Y-%m-%d'))
    media_diaria_anterior = len(df_concluidos_mes_anterior) / dias_uteis_mes_anterior if dias_uteis_mes_anterior > 0 else 0
    
    recorde_dia_valor = 0; recorde_dia_data = "N/A"; recorde_dia_qtd = 0
    if not df_concluidos_mes_atual.empty:
        producao_diaria = df_concluidos_mes_atual.groupby(df_concluidos_mes_atual[COLUNA_DATA_CONCLUSAO].dt.date).size()
        if not producao_diaria.empty:
            recorde_dia_valor = producao_diaria.max()
            recorde_dia_data_obj = producao_diaria.idxmax()
            recorde_dia_data = recorde_dia_data_obj.strftime('%d/%m/%Y')
            recorde_dia_qtd = df_concluidos_mes_atual[df_concluidos_mes_atual[COLUNA_DATA_CONCLUSAO].dt.date == recorde_dia_data_obj][COLUNA_QTD].sum()
            
    return {"total_mes_atual": total_mes_atual_pedidos, "total_mes_atual_qtd": total_mes_atual_qtd, "media_diaria_atual": media_diaria_atual, "media_diaria_qtd": media_diaria_qtd,
            "total_mes_anterior": len(df_concluidos_mes_anterior), "media_diaria_anterior": media_diaria_anterior,
            "recorde_dia_valor": recorde_dia_valor, "recorde_dia_data": recorde_dia_data, "recorde_dia_qtd": recorde_dia_qtd}

def calcular_dados_grafico(df_full):
    if df_full.empty or 'status_id' not in df_full.columns:
        return []
    
    # CORREÇÃO 4: Usar ID numérico para filtrar dados do gráfico
    STATUS_ID_CONCLUIDO = 4

    df_concluidos = df_full.dropna(subset=[COLUNA_DATA_CONCLUSAO]).copy()
    df_concluidos = df_concluidos[df_concluidos['status_id'] == STATUS_ID_CONCLUIDO]
    if df_concluidos.empty:
        return []

    datas_conclusao = pd.to_datetime(df_concluidos[COLUNA_DATA_CONCLUSAO])
    inicio_da_semana = datas_conclusao - pd.to_timedelta(datas_conclusao.dt.weekday, unit='D')
    df_concluidos['Semana'] = inicio_da_semana.dt.date
    semanal = df_concluidos.groupby('Semana')[COLUNA_QTD].sum()
    hoje = datetime.now(TZ).date()
    semanas_recentes = pd.to_datetime(pd.date_range(end=hoje, periods=4, freq='W-MON')).date
    semanal = semanal.reindex(semanas_recentes, fill_value=0)
    
    return list(semanal.items())

# --- STYLESHEET (Folha de Estilos) ---
STYLESHEET = f"""
    QMainWindow {{ background-color: #1C1C1C; }} QLabel {{ color: #E0E0E0; }}
    #Header {{ background-color: #2E2E2E; border-bottom: 2px solid #FF6600; }}
    #LogoLabel {{ padding: 5px; }} .SectionTitle {{ border-bottom: 2px solid; padding-bottom: 8px; margin-bottom: 10px; }}
    #PrioridadesTitle, #EmMontagemTitle, #PendentesTitle, #BacklogTitle, #AguardandoChegadaTitle {{ color: #FF6600; border-bottom-color: #FF6600; }}
    #ConcluidosTitle {{ color: #2ECC71; border-bottom-color: #2ECC71; }} #CanceladosTitle {{ color: #E74C3C; border-bottom-color: #E74C3C; }}
    #CounterLabel {{ color: #888888; font-style: italic; padding-top: 10px; }}
    #SideColumnFrame {{ background-color: #252525; border-radius: 8px; }} #ErrorLabel {{ color: #E74C3C; }}
    #Card {{ background-color: #2E2E2E; border: 1px solid #FF6600; border-radius: 8px; padding: 12px; }}
    #CardTitle {{ color: #FF8C33; }}
    #CardStatus_Backlog {{ color: #3498DB; }}
    #CardStatus_EmMontagem {{ color: #F39C12; }}
    #CardStatus_Urgente {{ color: #FF5733; }}
    #TotalLabel {{ color: #BDBDBD; margin-top: 10px; }}
    #DashboardFrame {{ border-top: 1px solid #444; margin-top: 10px; padding: 10px; }}
    #MetricaTitle, #KpiTitle {{ color: #FFFFFF; font-weight: bold; }} #MetricaValue, #KpiValue {{ color: #FF6600; }}
    #KpiRecorde {{ color: #3498DB; }}
    QProgressBar {{ border: 1px solid #555; border-radius: 5px; text-align: center; background-color: #2E2E2E; }}
    QProgressBar::chunk {{ background-color: #FF6600; border-radius: 4px; }}
    QProgressBar#currentWeek::chunk {{ background-color: #FFAA33; }}
    #NotificationLabel {{
        background-color: #2ECC71; color: white; border-radius: 5px;
        padding: 10px; font-weight: bold; font-size: {int(16 * SCALE_FACTOR)}px;
    }}
    #NotificationLabel[error="true"] {{
        background-color: #E74C3C;
    }}
"""

class PainelMtec(QMainWindow):
    # O restante da classe (toda a parte de UI com PySide6) não precisa de NENHUMA alteração.
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Painel de Produção MTEC"); self.setGeometry(100, 100, 1920, 1080);
        self.setStyleSheet(STYLESHEET)
        
        self.font_titulo = QFont("Inter", self.scale(16), QFont.Bold)
        self.font_item = QFont("Inter", self.scale(10))
        self.font_contador = QFont("Inter", self.scale(9))
        self.font_total = QFont("Inter", self.scale(9))
        self.font_metrica_titulo = QFont("Inter", self.scale(12), QFont.Bold)
        self.font_metrica_valor = QFont("Inter", self.scale(32), QFont.Bold)
        self.font_kpi_titulo = QFont("Inter", self.scale(11), QFont.Bold)
        self.font_kpi_valor = QFont("Inter", self.scale(12), QFont.Bold)

        self.main_container = QWidget(); self.error_container = QWidget(); self.is_showing_error = False
        
        self.setup_ui()
        self.create_persistent_widgets()
        self.setup_online_timer()
        self.atualizar_dados_e_ui()

    def scale(self, size):
        return int(size * SCALE_FACTOR)

    def setup_ui(self):
        self.central_widget = QWidget(); self.setCentralWidget(self.central_widget); layout = QVBoxLayout(self.central_widget); layout.setContentsMargins(0,0,0,0); layout.setSpacing(0)
        self.main_container = QWidget(); self.error_container = QWidget(); self.is_showing_error = False
        main_layout = QVBoxLayout(self.main_container); main_layout.setContentsMargins(0, 0, 0, 0); main_layout.setSpacing(0)
        
        header = QWidget(); header.setObjectName("Header"); header.setFixedHeight(self.scale(60)); header_layout = QHBoxLayout(header); header_layout.setContentsMargins(20, 0, 20, 0)
        
        logo_label = QLabel("mtec."); logo_label.setObjectName("LogoLabel"); logo_label.setFont(QFont("Inter", self.scale(22), QFont.Bold)); header_layout.addWidget(logo_label); header_layout.addStretch(); main_layout.addWidget(header)

        self.body_widget = QWidget()
        self.body_layout = QHBoxLayout(self.body_widget)
        self.body_layout.setContentsMargins(self.scale(15), self.scale(15), self.scale(15), self.scale(15)); self.body_layout.setSpacing(self.scale(20))
        main_layout.addWidget(self.body_widget, 1)

        dashboard_frame = QFrame(); dashboard_frame.setObjectName("DashboardFrame"); dashboard_frame.setFixedHeight(self.scale(317)); self.dashboard_layout = QHBoxLayout(dashboard_frame); main_layout.addWidget(dashboard_frame)
        self.setup_ui_columns()
        
        error_page_layout = QVBoxLayout(self.error_container); self.error_label = QLabel(); self.error_label.setObjectName("ErrorLabel"); self.error_label.setAlignment(Qt.AlignCenter); self.error_label.setWordWrap(True);
        self.error_label.setFont(QFont("Inter", self.scale(18), QFont.Bold)); error_page_layout.addWidget(self.error_label)
        layout.addWidget(self.main_container); layout.addWidget(self.error_container); self.error_container.hide()

        self.notification_label = QLabel(self); self.notification_label.setObjectName("NotificationLabel"); self.notification_label.setWordWrap(True); self.notification_label.hide()

    def setup_ui_columns(self):
        self.prioridades_layout = QVBoxLayout()
        self.prioridades_layout.setSpacing(self.scale(15))
        self.backlog_layout = QVBoxLayout()
        self.aguardando_chegada_layout = QVBoxLayout()
        self.pendentes_layout = QVBoxLayout()
        self.em_montagem_container = QWidget()
        self.em_montagem_layout = QVBoxLayout(self.em_montagem_container)
        self.em_montagem_layout.setContentsMargins(0, self.scale(20), 0, 0)
        self.em_montagem_layout.setSpacing(0)
        grid_layout = QGridLayout()
        grid_layout.setSpacing(self.scale(20))
        grid_layout.addLayout(self.backlog_layout, 0, 0)
        grid_layout.addLayout(self.aguardando_chegada_layout, 0, 1)
        grid_layout.addWidget(self.em_montagem_container, 1, 0)
        grid_layout.addLayout(self.pendentes_layout, 1, 1)
        grid_layout.setColumnStretch(0, 1)
        grid_layout.setColumnStretch(1, 1)
        grid_container_layout = QVBoxLayout()
        grid_container_layout.addLayout(grid_layout)
        grid_container_layout.addStretch()
        self.body_layout.addLayout(self.prioridades_layout, 2)
        self.body_layout.addLayout(grid_container_layout, 2)
        side_column_frame = QFrame()
        side_column_frame.setObjectName("SideColumnFrame")
        side_column_frame.setFixedWidth(self.scale(300))
        self.side_layout = QVBoxLayout(side_column_frame)
        self.concluidos_layout = QVBoxLayout()
        self.cancelados_layout = QVBoxLayout()
        self.side_layout.addLayout(self.concluidos_layout)
        self.side_layout.addStretch(1)
        linea_separadora = QFrame()
        linea_separadora.setFrameShape(QFrame.HLine)
        linea_separadora.setFrameShadow(QFrame.Sunken)
        linea_separadora.setStyleSheet("background-color: #444; min-height: 1px; border: none;")
        self.side_layout.addWidget(linea_separadora)
        self.side_layout.addSpacing(20)
        self.side_layout.addLayout(self.cancelados_layout)
        self.side_layout.addStretch(2)
        self.body_layout.addWidget(side_column_frame)
        self.metricas_layout = QVBoxLayout()
        self.grafico_layout = QVBoxLayout()
        self.kpi_layout = QVBoxLayout()
        self.dashboard_layout.addLayout(self.metricas_layout, 1)
        self.dashboard_layout.addLayout(self.grafico_layout, 2)
        self.dashboard_layout.addStretch(1)
        self.dashboard_layout.addLayout(self.kpi_layout, 1)
    
    def create_persistent_widgets(self):
        self.priority_cards = []
        self.em_montagem_labels, self.pendentes_labels, self.backlog_labels, self.aguardando_chegada_labels = [], [], [], []
        self.concluidos_labels, self.cancelados_labels = [], []
        
        self.prioridades_layout.addWidget(self.criar_titulo("PRIORIDADES", "PrioridadesTitle"))
        self.em_montagem_layout.addWidget(self.criar_titulo("EM MONTAGEM FORA DA PRIORIDADE", "EmMontagemTitle"))
        self.pendentes_layout.addWidget(self.criar_titulo("PENDENTES", "PendentesTitle"))
        self.backlog_layout.addWidget(self.criar_titulo("BACKLOG", "BacklogTitle"))
        self.aguardando_chegada_layout.addWidget(self.criar_titulo("AGUARDANDO CHEGADA", "AguardandoChegadaTitle"))
        self.concluidos_layout.addWidget(self.criar_titulo("ÚLTIMOS CONCLUÍDOS", "ConcluidosTitle"))
        self.cancelados_layout.addWidget(self.criar_titulo("ÚLTIMOS CANCELADOS", "CanceladosTitle"))
        
        for _ in range(4):
            card = QFrame(); card.setObjectName("Card"); card_layout = QVBoxLayout(card); card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed); card.setFixedHeight(self.scale(217))
            pedido_label = QLabel(); pedido_label.setFont(QFont("Inter", self.scale(15), QFont.Bold)); pedido_label.setObjectName("CardTitle")
            status_label = QLabel(); status_label.setFont(QFont("Inter", self.scale(12)))
            servico_label = QLabel(); servico_label.setFont(QFont("Inter", self.scale(12))); servico_label.setWordWrap(True)
            equipamento_label = QLabel(); equipamento_label.setFont(QFont("Inter", self.scale(12)))
            imagem_label = QLabel(); imagem_label.setFont(QFont("Inter", self.scale(12)))
            qtd_label = QLabel(); qtd_label.setFont(QFont("Inter", self.scale(20)))
            
            info_layout = QHBoxLayout()
            info_layout.addWidget(imagem_label)
            info_layout.addStretch()
            info_layout.addWidget(qtd_label)

            card_layout.addWidget(pedido_label)
            card_layout.addWidget(status_label)
            card_layout.addWidget(equipamento_label)
            card_layout.addWidget(servico_label)
            card_layout.addLayout(info_layout)
            
            refs = {'frame': card, 'pedido': pedido_label, 'status': status_label, 
                    'servico': servico_label, 'equipamento': equipamento_label, 
                    'imagem': imagem_label, 'qtd': qtd_label}
                    
            self.priority_cards.append(refs)
            self.prioridades_layout.addWidget(card)
            card.hide()
        self.prioridades_layout.addStretch()

        self.em_montagem_counter = self.create_list_widgets(self.em_montagem_layout, self.em_montagem_labels, 5)
        self.pendentes_counter = self.create_list_widgets(self.pendentes_layout, self.pendentes_labels, 5)
        self.backlog_counter = self.create_list_widgets(self.backlog_layout, self.backlog_labels, 5)
        self.aguardando_chegada_counter = self.create_list_widgets(self.aguardando_chegada_layout, self.aguardando_chegada_labels, 5)
        self.concluidos_counter, self.concluidos_total = self.create_side_list_widgets(self.concluidos_layout, self.concluidos_labels, 5)
        self.cancelados_counter, self.cancelados_total = self.create_side_list_widgets(self.cancelados_layout, self.cancelados_labels, 5)
        self.create_dashboard_widgets()

    def create_list_widgets(self, layout, label_list, count):
        for _ in range(count):
            label = QLabel(); label.setFont(self.font_item); label.hide()
            layout.addWidget(label)
            label_list.append(label)
        counter = QLabel(); counter.setObjectName("CounterLabel"); counter.setFont(self.font_contador); counter.hide()
        layout.addWidget(counter)
        layout.addStretch()
        return counter
        
    def create_side_list_widgets(self, layout, label_list, count):
        for _ in range(count):
            label = QLabel(); label.setFont(self.font_item); label.hide()
            layout.addWidget(label)
            label_list.append(label)
        counter = QLabel(); counter.setObjectName("CounterLabel"); counter.setFont(self.font_contador); counter.hide()
        layout.addWidget(counter)
        total = QLabel(); total.setObjectName("TotalLabel"); total.setFont(self.font_total); total.hide()
        layout.addWidget(total)
        layout.addStretch(1)
        return counter, total

    def create_dashboard_widgets(self):
        self.metricas_layout.addWidget(self.criar_titulo("Total Concluído no Mês", "MetricaTitle"))
        self.total_mes_valor = QLabel(); self.total_mes_valor.setObjectName("MetricaValue"); self.total_mes_valor.setFont(self.font_metrica_valor)
        self.metricas_layout.addWidget(self.total_mes_valor)
        self.metricas_layout.addStretch(1)
        self.metricas_layout.addWidget(self.criar_titulo("Média Diária no Mês", "MetricaTitle"))
        self.media_diaria_valor = QLabel(); self.media_diaria_valor.setObjectName("MetricaValue"); self.media_diaria_valor.setFont(self.font_metrica_valor)
        self.metricas_layout.addWidget(self.media_diaria_valor)
        self.metricas_layout.addStretch(1)
        self.grafico_layout.addWidget(self.criar_titulo(f"Desempenho Semanal (Meta: {META_SEMANAL} máq.)", ""))
        self.weekly_progress_widgets = []
        for _ in range(4):
            label_semana = QLabel(); label_semana.setFont(QFont("Inter", self.scale(10)))
            progress_bar = QProgressBar(); progress_bar.setRange(0, META_SEMANAL); progress_bar.setTextVisible(False); progress_bar.setFixedHeight(self.scale(18)); progress_bar.setMaximumWidth(self.scale(500))
            self.grafico_layout.addWidget(label_semana)
            self.grafico_layout.addWidget(progress_bar)
            refs = {'label': label_semana, 'bar': progress_bar}
            self.weekly_progress_widgets.append(refs)
            label_semana.hide(); progress_bar.hide()
        self.grafico_layout.addStretch()
        self.kpi_layout.addWidget(self.criar_titulo("Recorde Diário no Mês", "KpiTitle"))
        self.recorde_valor = QLabel(); self.recorde_valor.setObjectName("KpiValue"); self.recorde_valor.setFont(self.font_kpi_valor)
        self.kpi_layout.addWidget(self.recorde_valor)
        self.kpi_layout.addStretch()

    def criar_titulo(self, texto, object_name):
        label = QLabel(f"<b>{texto}</b>"); label.setObjectName(object_name); label.setFont(self.font_titulo); label.setProperty("class", "SectionTitle")
        return label
        
    def setup_online_timer(self):
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.atualizar_dados_e_ui)
        self.update_timer.start(10000)
        print("Modo online: O painel será atualizado a cada 10 segundos.")

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_F11:
            if self.isFullScreen():
                self.showMaximized()
            else:
                self.showFullScreen()
        super().keyPressEvent(event)

    def atualizar_dados_e_ui(self):
        print("\n--- INICIANDO CICLO DE ATUALIZAÇÃO ---")
        try:
            df_full, df_principal, df_concluidos, df_cancelados, totais_concluidos, totais_cancelados = carregar_dados()
            
            if self.is_showing_error: self.clear_error_message()
            
            self.update_colunas(df_principal, df_concluidos, df_cancelados, totais_concluidos, totais_cancelados)
            
            metricas = calcular_metricas_dashboard(df_full)
            dados_grafico = calcular_dados_grafico(df_full)
            self.update_dashboard(metricas, dados_grafico)
            
            print("--- CICLO DE ATUALIZAÇÃO CONCLUÍDO ---")
        except Exception as e:
            print(f"ERRO CRÍTICO NO CICLO DE ATUALIZAÇÃO: {e}")
            traceback.print_exc()
            self.mostrar_erro(str(e))

    def mostrar_erro(self, message):
        self.main_container.hide(); self.error_container.show(); self.is_showing_error = True
        self.error_label.setText(f"Erro ao carregar dados:\n\n{message}"); self.error_label.setAlignment(Qt.AlignCenter)
        print(f"ERRO EXIBIDO: {message}")

    def clear_error_message(self):
        self.error_container.hide(); self.main_container.show(); self.is_showing_error = False
    
    def update_colunas(self, df_principal, df_concluidos, df_cancelados, totais_concluidos, totais_cancelados):
        status_excluidos_da_prioridade = [STATUS_AGUARDANDO_CHEGADA.lower(), STATUS_PENDENTE.lower()]
        
        df_prioridades = df_principal[~df_principal[COLUNA_STATUS].str.lower().isin(status_excluidos_da_prioridade)]
        
        pedidos_nos_cards_ids = df_prioridades.head(len(self.priority_cards))[COLUNA_PEDIDO_ID].tolist()

        self.update_cards_prioridade(df_prioridades)

        df_em_montagem_base = df_principal[df_principal[COLUNA_STATUS].str.lower() == STATUS_EM_MONTAGEM.lower()]
        df_em_montagem_filtrado = df_em_montagem_base[~df_em_montagem_base[COLUNA_PEDIDO_ID].isin(pedidos_nos_cards_ids)]

        if df_em_montagem_filtrado.empty:
            self.em_montagem_container.hide()
        else:
            self.em_montagem_container.show()
            self.update_lista_vertical(df_em_montagem_filtrado, self.em_montagem_labels, self.em_montagem_counter)

        df_pendentes = df_principal[df_principal[COLUNA_STATUS].str.lower() == STATUS_PENDENTE.lower()]
        self.update_lista_vertical(df_pendentes, self.pendentes_labels, self.pendentes_counter)

        df_backlog_base = df_principal[df_principal[COLUNA_STATUS].str.lower() == STATUS_BACKLOG.lower()]
        df_backlog_filtrado = df_backlog_base[~df_backlog_base[COLUNA_PEDIDO_ID].isin(pedidos_nos_cards_ids)]
        self.update_lista_vertical(df_backlog_filtrado, self.backlog_labels, self.backlog_counter)

        df_aguardando_chegada = df_principal[df_principal[COLUNA_STATUS].str.lower() == STATUS_AGUARDANDO_CHEGADA.lower()]
        self.update_lista_vertical(df_aguardando_chegada, self.aguardando_chegada_labels, self.aguardando_chegada_counter)

        self.update_lista_lateral(df_concluidos, self.concluidos_labels, self.concluidos_counter, self.concluidos_total, totais_concluidos)
        self.update_lista_lateral(df_cancelados, self.cancelados_labels, self.cancelados_counter, self.cancelados_total, totais_cancelados)

    def update_cards_prioridade(self, df):
        if df.empty:
            for card_ref in self.priority_cards:
                card_ref['frame'].hide()
            return
        
        for i, (_, row) in enumerate(df.head(len(self.priority_cards)).iterrows()):
            card_ref = self.priority_cards[i]
            
            titulo_card = f"<b>PV: {row[COLUNA_PV]}</b> ({row['Prioridade_Display']}ª Prioridade)"
            if row.get('is_urgent', False):
                titulo_card = f"<b>PV: {row[COLUNA_PV]}</b> <font color='#E74C3C'>(URGENTE)</font>"

            card_ref['pedido'].setText(titulo_card)
            card_ref['status'].setText(f"<font color='#BDBDBD'>Status: </font><span style='color: white; font-weight: bold;'>{row[COLUNA_STATUS]}</span>")
            card_ref['servico'].setText(f"<font color='#BDBDBD'>Serviço: </font>{row[COLUNA_SERVICO]}")
            card_ref['equipamento'].setText(f"<font color='#BDBDBD'>Equipamento: </font>{row[COLUNA_EQUIPAMENTO]}")
            card_ref['imagem'].setText(f"<font color='#BDBDBD'>Imagem: </font>{row.get(COLUNA_IMAGEM, 'N/A')}")
            card_ref['qtd'].setText(f"<font color='#BDBDBD'><b>{row[COLUNA_QTD]}</b> máq.</font>")
            card_ref['frame'].show()

        for j in range(len(df.head(len(self.priority_cards))), len(self.priority_cards)):
            self.priority_cards[j]['frame'].hide()

    def update_lista_vertical(self, df, label_list, counter_label):
        if df.empty:
            for label in label_list: label.hide()
            counter_label.hide()
            return
        
        for i, (_, row) in enumerate(df.head(len(label_list)).iterrows()):
            label = label_list[i]
            
            texto_label = f"<b>PV: {row[COLUNA_PV]}</b> <font color='#FF6600'>({row[COLUNA_QTD]} máq.)</font>"
            if row.get('is_urgent', False):
                texto_label += " <font color='#E74C3C'>🔥</font>"
                
            label.setText(texto_label)
            label.show()
        
        for j in range(len(df.head(len(label_list))), len(label_list)):
            label_list[j].hide()

        if len(df) > len(label_list):
            restantes = len(df) - len(label_list)
            counter_label.setText(f"+{restantes} pedidos...")
            counter_label.show()
        else:
            counter_label.hide()
    
    def update_lista_lateral(self, df, label_list, counter_label, total_label, totais):
        if df.empty:
            for label in label_list: label.hide()
            counter_label.hide()
        else:
            for i, (_, row) in enumerate(df.head(len(label_list)).iterrows()):
                label = label_list[i]
                texto = f"<b>PV: {row[COLUNA_PV]}</b> <font color='#2ECC71'>({row[COLUNA_QTD]} máq.)</font>"
                label.setText(texto); label.show()

            for j in range(len(df.head(len(label_list))), len(label_list)):
                label_list[j].hide()
            
            if len(df) > len(label_list):
                restantes = len(df) - len(label_list)
                counter_label.setText(f"+{restantes}..."); counter_label.show()
            else:
                counter_label.hide()

        teravix, pv, total, teravix_qtd, pv_qtd, total_qtd = totais
        texto_total = (f"<font color='#FF6600'>TERAVIX:</font> {teravix} ({teravix_qtd})<br>"
                       f"<font color='#FF6600'>PV:</font> {pv} ({pv_qtd})<br>"
                       f"<b><font color='#3498DB'>TOTAL DIA:</font></b> <b>{total} ({total_qtd})</b>")
        total_label.setText(texto_total)
        total_label.show()

    def update_dashboard(self, metricas, dados_grafico):
        self.total_mes_valor.setText(f"{metricas['total_mes_atual']:.0f} " \
                                     f"<font color='#999' style='font-size:{self.scale(15)}px;'>({metricas['total_mes_atual_qtd']:.0f} máq.)</font>")
        self.media_diaria_valor.setText(f"{metricas['media_diaria_atual']:.1f} " \
                                        f"<font color='#999' style='font-size:{self.scale(15)}px;'>({metricas['media_diaria_qtd']:.1f} máq.)</font>")

        start_of_current_week = (datetime.now(TZ).date() - timedelta(days=datetime.now(TZ).weekday()))
        for i, (data, valor) in enumerate(dados_grafico):
            widget_ref = self.weekly_progress_widgets[i]
            fim_semana = data + timedelta(days=6)
            texto_semana = f"Semana {data.strftime('%d/%m')} a {fim_semana.strftime('%d/%m')}"
            is_current_week = data == start_of_current_week
            if is_current_week:
                texto_semana = f"<b>▶ {texto_semana}</b>"
            
            widget_ref['label'].setText(f"{texto_semana}: <b>{int(valor)}</b>")
            widget_ref['bar'].setValue(min(int(valor), META_SEMANAL))
            widget_ref['bar'].setObjectName("currentWeek" if is_current_week else "")
            widget_ref['bar'].setStyle(QApplication.style())
            
            widget_ref['label'].show()
            widget_ref['bar'].show()

        for j in range(len(dados_grafico), len(self.weekly_progress_widgets)):
            self.weekly_progress_widgets[j]['label'].hide()
            self.weekly_progress_widgets[j]['bar'].hide()
            
        recorde_valor_html = f"{metricas['recorde_dia_valor']} pedidos " \
                             f"<font color='#999'>({metricas['recorde_dia_qtd']} máq.)</font><br>" \
                             f"<span id='KpiRecorde'>{metricas['recorde_dia_data']}</span>"
        self.recorde_valor.setText(recorde_valor_html)


if __name__ == "__main__":
    locale.setlocale(locale.LC_ALL, 'pt_BR.UTF-8')
    app = QApplication(sys.argv)
    window = PainelMtec()
    window.showFullScreen() 
    sys.exit(app.exec())


from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash
from painel_tv_data import get_painel_data
from flask_cors import CORS
from sqlalchemy import create_engine, text, Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker
from functools import wraps
import os
from datetime import datetime
import pytz
from werkzeug.security import generate_password_hash, check_password_hash
import traceback

# Definir fuso horário de Brasília
fuso_brasilia = pytz.timezone("America/Sao_Paulo")

app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app)

# --- Configurações de Sessão ---
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or os.urandom(24)
app.config['SESSION_TYPE'] = 'filesystem'
app.config['PERMANENT_SESSION_LIFETIME'] = 3600

# --- Conexão com o Banco de Dados ---
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql+psycopg2://postgres:2025@localhost:5432/pedidos_db')
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# --- Definição das Tabelas (Modelos SQLAlchemy) ---
Base = declarative_base()

class UsuarioTb(Base):
    __tablename__ = 'usuario_tb'
    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False)
    password_hash = Column(String(256), nullable=False)
    nome_completo = Column(String(120))
    nivel_acesso = Column(String(50), default='operador', nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class StatusTd(Base):
    __tablename__ = 'status_td'
    id = Column(Integer, primary_key=True)
    nome_status = Column(String, nullable=False, unique=True)

class ImagemTd(Base):
    __tablename__ = 'imagem_td'
    id = Column(Integer, primary_key=True)
    nome = Column(String, nullable=False, unique=True)

class PedidosTb(Base):
    __tablename__ = 'pedidos_tb'
    id = Column(Integer, primary_key=True)
    codigo_pedido = Column(String, unique=True)
    equipamento = Column(String)
    pv = Column(String)
    descricao_servico = Column(String)
    status_id = Column(Integer, ForeignKey('status_td.id'))
    imagem_id = Column(Integer, ForeignKey('imagem_td.id'))
    data_criacao = Column(DateTime(timezone=True), default=lambda: datetime.now(fuso_brasilia))
    data_conclusao = Column(DateTime(timezone=True))
    quantidade = Column(Integer)
    prioridade = Column(Integer, nullable=True)
    prioridade_antiga = Column(Integer, nullable=True)
    perfil_alteracao = Column(String)
    urgente = Column(Boolean, default=False)
    tem_office = Column(Boolean, default=False)
    criado_por = Column(String) # <--- 1. COLUNA ADICIONADA AO MODELO

class HistoricoStatusTb(Base):
    __tablename__ = 'historico_status_tb'
    id = Column(Integer, primary_key=True)
    pedido_id = Column(Integer, ForeignKey('pedidos_tb.id'))
    status_anterior = Column(Integer)
    status_alterado = Column(Integer)
    data_mudanca = Column(DateTime(timezone=True), default=lambda: datetime.now(fuso_brasilia))
    alterado_por = Column(String)

# --- FUNÇÃO PARA POPULAR DADOS INICIAIS ---
def popular_dados_iniciais(db_session):
    status_iniciais = ["Aguardando Chegada", "Backlog", "Em Montagem", "Concluído", "Pendente", "Cancelado"]
    imagens_iniciais = ["W11 PRO", "W11 PRO ETQ", "Linux", "SLUI (SOLUÇÃO DE PROBLEMAS)", "FREEDOS"]
    try:
        if db_session.query(StatusTd).count() == 0:
            for nome in status_iniciais: db_session.add(StatusTd(nome_status=nome))
            db_session.commit()
        if db_session.query(ImagemTd).count() == 0:
            for nome in imagens_iniciais: db_session.add(ImagemTd(nome=nome))
            db_session.commit()
    except Exception as e:
        db_session.rollback()

with app.app_context():
    Base.metadata.create_all(engine)
    db_sess = SessionLocal()
    try:
        popular_dados_iniciais(db_sess)
    finally:
        db_sess.close()

# --- DECORATORS E ROTAS DE AUTENTICAÇÃO ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'): return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('nivel_acesso') != 'admin':
            flash('Acesso restrito a administradores.', 'warning')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username, password = request.form.get("username"), request.form.get("password")
        db_session = SessionLocal()
        try:
            user = db_session.query(UsuarioTb).filter_by(username=username).first()
            if user and user.check_password(password):
                session.update({'logged_in': True, 'username': user.username, 'nivel_acesso': user.nivel_acesso})
                flash("Login efetuado com sucesso!", "success")
                return redirect(url_for('home'))
            else:
                flash("Credenciais inválidas.", "danger")
        finally:
            db_session.close()
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Sessão terminada com sucesso.", "success")
    return redirect(url_for('login'))

# --- ROTAS PRINCIPAIS E DA API ---
@app.route("/")
@login_required
def home(): return render_template("index.html")

@app.route("/painel-tv")
@login_required
def painel_tv_page(): return render_template("painel_tv.html")

@app.route("/api/painel-tv-dados")
@login_required
def painel_tv_api(): return jsonify(get_painel_data())

@app.route("/usuarios")
@login_required
@admin_required
def usuarios_page(): return render_template("usuarios.html")

# --- ROTAS DA API PARA USUÁRIOS (CRUD COMPLETO) ---
@app.route("/api/usuarios", methods=['GET', 'POST'])
@login_required
@admin_required
def handle_usuarios():
    db_session = SessionLocal()
    try:
        if request.method == 'GET':
            usuarios_db = db_session.query(UsuarioTb).order_by(UsuarioTb.id).all()
            return jsonify([{"id": u.id, "username": u.username, "nome_completo": u.nome_completo, "nivel_acesso": u.nivel_acesso} for u in usuarios_db])
        
        elif request.method == 'POST':
            data = request.get_json()
            if not all(data.get(k) for k in ['username', 'nome_completo', 'password', 'nivel_acesso']):
                return jsonify({'erro': 'Todos os campos são obrigatórios.'}), 400
            if db_session.query(UsuarioTb).filter_by(username=data['username']).first():
                return jsonify({'erro': f'O username "{data["username"]}" já está em uso.'}), 409
            
            novo_usuario = UsuarioTb(username=data['username'], nome_completo=data['nome_completo'], nivel_acesso=data['nivel_acesso'])
            novo_usuario.set_password(data['password'])
            db_session.add(novo_usuario)
            db_session.commit()
            return jsonify({'mensagem': f'Usuário {data["username"]} criado com sucesso!'}), 201
    except Exception as e:
        db_session.rollback()
        return jsonify({'erro': f'Ocorreu um erro interno: {e}'}), 500
    finally:
        db_session.close()

@app.route('/api/usuarios/<int:user_id>', methods=['PUT', 'DELETE'])
@login_required
@admin_required
def handle_single_usuario(user_id):
    db_session = SessionLocal()
    try:
        usuario = db_session.query(UsuarioTb).filter_by(id=user_id).first()
        if not usuario: return jsonify({'erro': 'Usuário não encontrado.'}), 404
        if usuario.username == session.get('username'): return jsonify({'erro': 'Não é permitido modificar o próprio utilizador logado.'}), 403

        if request.method == 'PUT':
            data = request.get_json()
            if 'nome_completo' in data: usuario.nome_completo = data['nome_completo']
            if 'nivel_acesso' in data: usuario.nivel_acesso = data['nivel_acesso']
            if data.get('password'): usuario.set_password(data['password'])
            db_session.commit()
            return jsonify({'mensagem': f'Utilizador {usuario.username} atualizado com sucesso!'})

        elif request.method == 'DELETE':
            username_deletado = usuario.username
            db_session.delete(usuario)
            db_session.commit()
            return jsonify({'mensagem': f'Utilizador {username_deletado} excluído com sucesso!'})
    except Exception as e:
        db_session.rollback()
        return jsonify({'erro': f'Ocorreu um erro interno: {e}'}), 500
    finally:
        db_session.close()

# --- ROTAS DA API PARA PEDIDOS ---
@app.route("/pedidos", methods=["GET"])
@login_required
def get_pedidos():
    args = request.args
    filtro_tab, busca_texto, busca_mes, busca_ano = args.get('filtro'), args.get('busca'), args.get('mes'), args.get('ano')
    params, where_conditions = {}, []

    if filtro_tab == 'concluido': where_conditions.append("p.status_id = 4")
    elif filtro_tab == 'cancelado': where_conditions.append("p.status_id = 6")
    else:
        where_conditions.append("p.status_id NOT IN (4, 6)")
        if not busca_mes and not busca_ano:
            where_conditions.extend(["EXTRACT(MONTH FROM p.data_criacao) = EXTRACT(MONTH FROM NOW())", "EXTRACT(YEAR FROM p.data_criacao) = EXTRACT(YEAR FROM NOW())"])

    if busca_texto:
        where_conditions.append("(p.pv ILIKE :busca OR p.codigo_pedido ILIKE :busca)")
        params['busca'] = f"%{busca_texto}%"
    
    coluna_data = "p.data_criacao" if filtro_tab != 'concluido' and filtro_tab != 'cancelado' else "p.data_conclusao"
    if busca_mes:
        where_conditions.append(f"EXTRACT(MONTH FROM {coluna_data}) = :mes")
        params['mes'] = int(busca_mes)
    if busca_ano and busca_ano.isdigit():
        where_conditions.append(f"EXTRACT(YEAR FROM {coluna_data}) = :ano")
        params['ano'] = int(busca_ano)

    query_sql = f"""
        SELECT p.*, s.nome_status as status, i.nome as imagem_nome FROM public.pedidos_tb p
        LEFT JOIN public.status_td s ON p.status_id = s.id 
        LEFT JOIN public.imagem_td i ON p.imagem_id = i.id
        WHERE {' AND '.join(where_conditions)} ORDER BY p.urgente DESC, p.prioridade ASC, p.data_criacao ASC
    """
    with engine.connect() as conn:
        pedidos = [dict(row._mapping) for row in conn.execute(text(query_sql), params)]
    return jsonify(pedidos)

@app.route("/pedidos", methods=["POST"])
@login_required
def add_pedido():
    data = request.json
    data_criacao = datetime.now(fuso_brasilia)
    username = session.get('username', 'Anónimo')

    with engine.connect() as conn, conn.begin():
        max_p = conn.execute(text("""
            SELECT COALESCE(MAX(prioridade), 0) FROM public.pedidos_tb
            WHERE EXTRACT(MONTH FROM data_criacao) = :mes AND EXTRACT(YEAR FROM data_criacao) = :ano
        """), {"mes": data_criacao.month, "ano": data_criacao.year}).scalar_one()
        data['prioridade'] = max_p + 1
        
        # --- 2. CORREÇÃO NO INSERT ---
        novo_pedido_id = conn.execute(text("""
            INSERT INTO public.pedidos_tb (pv, equipamento, quantidade, descricao_servico, status_id, imagem_id, perfil_alteracao, data_criacao, urgente, prioridade, tem_office, criado_por) 
            VALUES (:pv, :eq, :qtd, :serv, :s_id, :i_id, :perfil, :data_c, :urg, :prio, :office, :criado_por) RETURNING id
        """), {
            **data, 
            "eq": data["equipamento"], 
            "qtd": data["quantidade"], 
            "serv": data["descricao_servico"], 
            "s_id": data["status_id"], 
            "i_id": data["imagem_id"], 
            "perfil": username, 
            "data_c": data_criacao, 
            "urg": data.get('urgente', False), 
            "prio": data['prioridade'], 
            "office": data.get('tem_office', False),
            "criado_por": username
        }).scalar_one()
        
        conn.execute(text("INSERT INTO public.historico_status_tb (pedido_id, status_alterado, data_mudanca, alterado_por) VALUES (:p_id, :s_alt, :data_m, :por)"),
            {"p_id": novo_pedido_id, "s_alt": data["status_id"], "data_m": data_criacao, "por": session.get('username')})
    return jsonify({"mensagem": "Pedido adicionado com sucesso!"}), 201

@app.route("/pedidos/<int:pedido_id>", methods=["PUT"])
@login_required
def update_pedido(pedido_id):
    data = request.json
    with engine.connect() as conn, conn.begin():
        pedido_atual = conn.execute(text("SELECT status_id, prioridade, prioridade_antiga, data_criacao FROM pedidos_tb WHERE id = :id"), {"id": pedido_id}).fetchone()
        if not pedido_atual: return jsonify({"erro": "Pedido não encontrado"}), 404

        status_anterior_id, p_atual, p_antiga_salva, data_c = pedido_atual
        novo_status_id = int(data.get("status_id"))
        params_mes_ano = {"mes": data_c.month, "ano": data_c.year}

        if novo_status_id in [4, 6] and status_anterior_id not in [4, 6] and p_atual:
            conn.execute(text("UPDATE public.pedidos_tb SET prioridade_antiga = :p_atual, prioridade = NULL WHERE id = :id"), {"p_atual": p_atual, "id": pedido_id})
            conn.execute(text("UPDATE public.pedidos_tb SET prioridade = prioridade - 1 WHERE prioridade > :p_removida AND EXTRACT(MONTH from data_criacao) = :mes AND EXTRACT(YEAR from data_criacao) = :ano"), {"p_removida": p_atual, **params_mes_ano})
            data['prioridade'] = None
        elif status_anterior_id in [4, 6] and novo_status_id not in [4, 6]:
            p_a_restaurar = p_antiga_salva if p_antiga_salva is not None else 9999
            conn.execute(text("UPDATE public.pedidos_tb SET prioridade = prioridade + 1 WHERE prioridade >= :p_restaurada AND EXTRACT(MONTH from data_criacao) = :mes AND EXTRACT(YEAR from data_criacao) = :ano"), {"p_restaurada": p_a_restaurar, **params_mes_ano})
            data['prioridade'] = p_a_restaurar

        params = {**data, "id": pedido_id, "perfil": session.get('username')}
        query_update_sql = "UPDATE public.pedidos_tb SET pv=:pv, equipamento=:equipamento, quantidade=:quantidade, descricao_servico=:descricao_servico, status_id=:status_id, imagem_id=:imagem_id, perfil_alteracao=:perfil, urgente=:urgente, prioridade=:prioridade, tem_office=:tem_office"
        
        if novo_status_id in [4, 6]:
            query_update_sql += ", data_conclusao = :data_con"
            params["data_con"] = datetime.now(fuso_brasilia)
        elif status_anterior_id in [4, 6] and novo_status_id not in [4, 6]:
            query_update_sql += ", data_conclusao = NULL, prioridade_antiga = NULL"
        
        conn.execute(text(f"{query_update_sql} WHERE id=:id"), params)

        if status_anterior_id != novo_status_id:
            conn.execute(text("INSERT INTO public.historico_status_tb (pedido_id, status_anterior, status_alterado, data_mudanca, alterado_por) VALUES (:p_id, :s_ant, :s_alt, :data_m, :por)"),
                {"p_id": pedido_id, "s_ant": status_anterior_id, "s_alt": novo_status_id, "data_m": datetime.now(fuso_brasilia), "por": session.get('username')})
    return jsonify({"mensagem": "Pedido atualizado!"})

@app.route("/pedidos/<int:pedido_id>", methods=["DELETE"])
@login_required
def delete_pedido(pedido_id):
    with engine.connect() as conn, conn.begin():
        pedido = conn.execute(text("SELECT prioridade, data_criacao FROM pedidos_tb WHERE id = :id"), {"id": pedido_id}).fetchone()
        conn.execute(text("DELETE FROM public.historico_status_tb WHERE pedido_id=:id"), {"id": pedido_id})
        conn.execute(text("DELETE FROM public.pedidos_tb WHERE id=:id"), {"id": pedido_id})
        if pedido and pedido.prioridade:
            conn.execute(text("UPDATE public.pedidos_tb SET prioridade = prioridade - 1 WHERE prioridade > :p_removida AND EXTRACT(MONTH from data_criacao) = :mes AND EXTRACT(YEAR from data_criacao) = :ano"),
                {"p_removida": pedido.prioridade, "mes": pedido.data_criacao.month, "ano": pedido.data_criacao.year})
    return jsonify({"mensagem": "Pedido deletado!"})

@app.route('/api/reordenar-prioridade', methods=['POST'])
@login_required
def reordenar_prioridade():
    data = request.get_json()
    pedido_id, nova_prioridade = data.get('pedido_id'), data.get('nova_prioridade')
    if not all([pedido_id, isinstance(nova_prioridade, int), nova_prioridade > 0]):
        return jsonify({'erro': 'Dados inválidos fornecidos.'}), 400

    with engine.connect() as conn, conn.begin():
        pedido = conn.execute(text("SELECT prioridade, data_criacao FROM pedidos_tb WHERE id = :id"), {"id": pedido_id}).fetchone()
        if not pedido or not pedido.prioridade: return jsonify({'erro': 'Pedido não encontrado ou não está na fila.'}), 404
        
        p_antiga, data_c = pedido
        if nova_prioridade == p_antiga: return jsonify({'mensagem': 'O pedido já está nesta posição.'})

        params = {"mes": data_c.month, "ano": data_c.year}
        filtro_mes_ano = "AND EXTRACT(MONTH from data_criacao) = :mes AND EXTRACT(YEAR from data_criacao) = :ano"
        if nova_prioridade < p_antiga:
            conn.execute(text(f"UPDATE pedidos_tb SET prioridade = prioridade + 1 WHERE prioridade >= :nova AND prioridade < :antiga {filtro_mes_ano}"), {"nova": nova_prioridade, "antiga": p_antiga, **params})
        else:
            conn.execute(text(f"UPDATE pedidos_tb SET prioridade = prioridade - 1 WHERE prioridade > :antiga AND prioridade <= :nova {filtro_mes_ano}"), {"nova": nova_prioridade, "antiga": p_antiga, **params})
        
        conn.execute(text("UPDATE pedidos_tb SET prioridade = :nova WHERE id = :id"), {"nova": nova_prioridade, "id": pedido_id})
    return jsonify({'mensagem': 'Prioridade atualizada com sucesso!'}), 200

# --- OUTRAS ROTAS DA API ---
@app.route("/pedidos/<int:pedido_id>/historico", methods=["GET"])
@login_required
def get_historico_pedido(pedido_id):
    query = """
        SELECT h.data_mudanca, h.alterado_por, COALESCE(s_ant.nome_status, 'CRIADO') as nome_status_anterior, s_alt.nome_status as nome_status_alterado
        FROM public.historico_status_tb h
        LEFT JOIN public.status_td s_ant ON h.status_anterior = s_ant.id
        LEFT JOIN public.status_td s_alt ON h.status_alterado = s_alt.id
        WHERE h.pedido_id = :pedido_id ORDER BY h.data_mudanca DESC
    """
    with engine.connect() as conn:
        historico = [dict(row._mapping) for row in conn.execute(text(query), {"pedido_id": pedido_id})]
    return jsonify(historico)

@app.route("/status", methods=["GET"])
@login_required
def get_status():
    with engine.connect() as conn:
        return jsonify([dict(row._mapping) for row in conn.execute(text("SELECT id, nome_status as nome FROM public.status_td ORDER BY id"))])

@app.route("/imagem", methods=["GET"])
@login_required
def get_imagens():
    with engine.connect() as conn:
        return jsonify([dict(row._mapping) for row in conn.execute(text("SELECT id, nome FROM public.imagem_td ORDER BY id"))])

@app.route("/api/gerar-relatorio", methods=['POST'])
@login_required
def gerar_relatorio_api():
    db_session = SessionLocal()
    try:
        data = request.get_json()
        start_date_str = data.get('start_date')
        end_date_str = data.get('end_date')

        if not start_date_str or not end_date_str:
            return jsonify({'error': 'As datas de início e fim são obrigatórias.'}), 400

        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').replace(hour=0, minute=0, second=0, tzinfo=fuso_brasilia)
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59, tzinfo=fuso_brasilia)
        
        # Query 1: Busca pedidos FINALIZADOS (concluídos/cancelados) DENTRO DO PERÍODO
        query_finalizadas = text("""
            SELECT
                s.nome_status as status,
                CASE WHEN p.equipamento ILIKE '%teravix%' THEN 'OP' ELSE 'PV' END as tipo,
                COUNT(DISTINCT p.pv) as total_pedidos,
                COALESCE(SUM(p.quantidade), 0) as total_unidades
            FROM pedidos_tb p
            JOIN status_td s ON p.status_id = s.id
            WHERE s.nome_status IN ('Concluído', 'Cancelado')
              AND p.data_conclusao BETWEEN :start_date AND :end_date
            GROUP BY status, tipo;
        """)
        
        # Query 2: Busca o ESTADO ATUAL dos pedidos em aberto (sem filtro de data)
        query_atuais = text("""
            SELECT
                CASE 
                    WHEN s.nome_status IN ('Backlog', 'Em Montagem') THEN 'Backlog'
                    ELSE s.nome_status 
                END as status_agrupado,
                CASE WHEN p.equipamento ILIKE '%teravix%' THEN 'OP' ELSE 'PV' END as tipo,
                COUNT(DISTINCT p.pv) as total_pedidos,
                COALESCE(SUM(p.quantidade), 0) as total_unidades
            FROM pedidos_tb p
            JOIN status_td s ON p.status_id = s.id
            WHERE s.nome_status IN ('Backlog', 'Em Montagem', 'Pendente')
            GROUP BY status_agrupado, tipo;
        """)

        result_finalizadas = db_session.execute(query_finalizadas, {"start_date": start_date, "end_date": end_date}).mappings().all()
        result_atuais = db_session.execute(query_atuais).mappings().all()

        # Estrutura de dados para armazenar os totais
        dados = {
            'realizadas': {'PV': None, 'OP': None},
            'canceladas': {'PV': None, 'OP': None},
            'backlog': {'PV': None, 'OP': None},
            'pendentes': {'PV': None, 'OP': None}
        }

        # Processa os resultados
        for row in result_finalizadas:
            categoria = 'realizadas' if row['status'] == 'Concluído' else 'canceladas'
            dados[categoria][row['tipo']] = {'pedidos': row['total_pedidos'], 'unidades': row['total_unidades']}
        
        for row in result_atuais:
            if row['status_agrupado'] == 'Backlog':
                dados['backlog'][row['tipo']] = {'pedidos': row['total_pedidos'], 'unidades': row['total_unidades']}
            elif row['status_agrupado'] == 'Pendente':
                dados['pendentes'][row['tipo']] = {'pedidos': row['total_pedidos'], 'unidades': row['total_unidades']}
        
        # Função auxiliar para formatar cada seção do relatório
        def construir_secao(titulo, dados_secao):
            texto = f"<strong><u>{titulo}:</u></strong>\n"
            if not dados_secao['PV'] and not dados_secao['OP']:
                return texto + "    • Nenhuma atividade.\n"
            if dados_secao['PV']:
                texto += f"    • {dados_secao['PV']['pedidos']} PV com {dados_secao['PV']['unidades']} unidades\n"
            if dados_secao['OP']:
                texto += f"    • {dados_secao['OP']['pedidos']} OP com {dados_secao['OP']['unidades']} unidades de Teravix\n"
            return texto

        # Monta o texto final, adicionando seções apenas se tiverem conteúdo
        data_formatada = end_date.strftime('%d/%m/%Y')
        if start_date_str != end_date_str:
            data_formatada = f"{start_date.strftime('%d/%m/%Y')} a {data_formatada}"

        partes_relatorio = [f"Relatório de Atividades - <u>{data_formatada}</u>", "=" * 40]
        
        partes_relatorio.append(construir_secao("Atividades Realizadas", dados['realizadas']))
        
        if dados['canceladas']['PV'] or dados['canceladas']['OP']:
            partes_relatorio.append(construir_secao("Atividades Canceladas", dados['canceladas']))
        
        if dados['pendentes']['PV'] or dados['pendentes']['OP']:
            partes_relatorio.append(construir_secao("Pendentes", dados['pendentes']))

        partes_relatorio.append(construir_secao("Backlog", dados['backlog']))

        relatorio_texto = "\n".join(partes_relatorio)

        return jsonify({'relatorio': relatorio_texto.strip().replace('\n', '<br>')})

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': f'Ocorreu um erro interno no servidor: {e}'}), 500
    finally:
        db_session.close()

# --- ROTA ADICIONADA PARA CORRIGIR O ERRO ---
@app.route("/relatorios")
@login_required
def relatorios_page():
    return render_template("relatorio.html")

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)

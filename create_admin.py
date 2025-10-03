import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from getpass import getpass
# CORREÇÃO: Importando do arquivo 'crud.py' em vez de 'app.py'
from crud import UsuarioTb, Base 

# --- Conexão com o Banco de Dados (use a mesma URL do seu app) ---
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql+psycopg2://postgres:2025@localhost:5432/pedidos_db')
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def adicionar_novo_usuario():
    """
    Este script adiciona um novo usuário ao banco de dados,
    permitindo definir seu nome completo e nível de acesso.
    """
    # Garante que a tabela de usuários exista
    print("Verificando se a tabela 'usuario_tb' existe...")
    Base.metadata.create_all(engine)
    print("Tabela pronta.")

    db_session = SessionLocal()
    try:
        print("\n--- Cadastro de Novo Usuário ---")
        
        username = input("Digite o username para o novo usuário: ")
        
        # Verifica se o username já existe no banco
        usuario_existente = db_session.query(UsuarioTb).filter_by(username=username).first()
        if usuario_existente:
            print(f"\nErro: O username '{username}' já está em uso. Operação cancelada.")
            return

        nome_completo = input(f"Digite o nome completo de '{username}': ")
        password = getpass("Digite a senha: ")
        confirm_password = getpass("Confirme a senha: ")

        if password != confirm_password:
            print("As senhas não coincidem. Operação cancelada.")
            return
            
        if not username or not password or not nome_completo:
            print("Username, nome completo e senha não podem ser vazios. Operação cancelada.")
            return

        # Pergunta e valida o nível de acesso
        nivel_acesso = ''
        while nivel_acesso not in ['admin', 'operador']:
            nivel_acesso = input("Qual o nível de acesso? (admin/operador): ").lower().strip()
            if nivel_acesso not in ['admin', 'operador']:
                print("Entrada inválida. Por favor, digite 'admin' ou 'operador'.")

        # Cria a nova instância do usuário
        novo_usuario = UsuarioTb(
            username=username,
            nome_completo=nome_completo,
            nivel_acesso=nivel_acesso # Define o nível de acesso escolhido
        )
        # Define a senha (o hash será calculado pelo método)
        novo_usuario.set_password(password)

        # Adiciona ao banco de dados
        db_session.add(novo_usuario)
        db_session.commit()

        print(f"\nUsuário '{username}' com nível '{nivel_acesso}' criado com sucesso!")

    except Exception as e:
        print(f"\nOcorreu um erro: {e}")
        db_session.rollback()
    finally:
        db_session.close()

if __name__ == "__main__":
    adicionar_novo_usuario()


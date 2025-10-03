# 📊 Painel de Produção MTEC

Um sistema completo para gerenciamento de ordens de produção, composto por:
- **Interface Web** para CRUD de pedidos.  
- **Painel de Visualização em tempo real (para TVs)**, ideal para acompanhamento na linha de produção.

---

## 🖼️ Telas do Projeto

### Interface Web de Gerenciamento
A interface web permite a criação, edição, exclusão e reordenação de pedidos de forma intuitiva e rápida.  

![Interface Web](./docs/interface-web.png)  
<sub>Tela principal da interface web, mostrando a lista de pedidos em andamento com opções de filtro e edição.</sub>

---

### Painel de Visualização (Dashboard para TV)
O painel é otimizado para telas grandes e atualiza automaticamente, mostrando o status da produção em tempo real para toda a equipe.  

![Painel TV](./docs/painel-tv.png)  
<sub>Dashboard de produção exibindo prioridades, status e métricas de desempenho.</sub>

---

## ✨ Funcionalidades Principais

- **Gerenciamento Completo (CRUD):** Criação, leitura, atualização e exclusão de pedidos.  
- **Controle de Prioridade:** Reordenação da fila de produção.  
- **Status de Urgência:** Destaque para pedidos críticos.  
- **Painel em Tempo Real:** Dashboard atualizado automaticamente.  
- **Histórico de Alterações:** Registro completo das mudanças.  
- **Filtros e Pesquisa:** Localize pedidos rapidamente por OP/PV, mês ou ano.  
- **Ambiente Dockerizado:** Instalação e execução consistentes via Docker.  

---

## 🛠️ Tecnologias Utilizadas

- **Backend:** Python (Flask)  
- **Banco de Dados:** PostgreSQL  
- **Frontend:** HTML5, CSS3, JavaScript, Bootstrap 5  
- **Dashboard (TV):** Python (PySide6 / Qt for Python)  
- **Containerização:** Docker & Docker Compose  
- **Análise de Dados (scripts):** Pandas  

---

## 🚀 Como Rodar o Projeto

### Pré-requisitos
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) instalado e em execução.
- [pgAdmin 4](https://www.pgadmin.org/download/pgadmin-4-windows/) instalado e em execução.

# Passos

### 1- Clone o repositório
```bash
git clone https://github.com/andersonskywalkr/painel_mtec.git
```

### 2- Entre na pasta do projeto
```bash
cd painel_mtec
```

### 3- Construa e inicie os contêineres
```bash
docker compose up -d --build
```
---

## 🌐 Acessando a Aplicação
- Interface web: [http://localhost:5000](http://localhost:5000)  

```Markdown
> ⚠️ **Atenção:** As credenciais de login não são públicas. Solicite-as ao administrador do sistema.
```
---

## 📥 Importando Dados Iniciais

```bash
docker compose exec app python app/migracao_dados.py
```
### Tabela status_tb
```bash
1	"Aguardando Chegada"
2	"Backlog"
3	"Em Montagem"
4	"Concluído"
5	"Pendente"
6	"Cancelado"
```
### Tabela imagem_tb
```bash
1	"W11 PRO"
2	"W11 PRO ETQ"
3	"Linux"
4	"SLUI (SOLUÇÃO DE PROBLEMAS)"
5	"FREEDOS"
```

---

## 🛑 Encerrando os Serviços

```bash
docker compose down
```
---

## 📂 Estrutura do Projeto
```plaintext
Copiar código
.
├── app/
│   └── migracao_dados.py       # Script para importar dados da planilha Excel
├── dados/
│   └── Status_dos_pedidos.xlsm # Planilha com dados de exemplo
├── templates/
│   ├── index.html              # Página principal da interface web
│   └── login.html              # Tela de login
├── crud.py                     # Backend principal da aplicação Flask
├── painel.py                   # Dashboard de visualização (TV)
├── Dockerfile                  # Configuração da imagem da aplicação
├── docker-compose.yml          # Orquestração dos serviços
└── requirements.txt            # Dependências do projeto
```

FROM python:3.9-slim

WORKDIR /app

# Copia da raiz do projeto
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copia da raiz do projeto
COPY . .

CMD ["flask", "run", "--host=0.0.0.0"]
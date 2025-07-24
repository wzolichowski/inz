FROM python:3.11-slim

WORKDIR /app

# Kopiujemy plik z zależnościami i instalujemy je
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopiujemy cały kod backendu
COPY . .

# Eksponujemy port 8000
EXPOSE 8000

ENV DATABASE_URL=[$DATABASE_URL]
# Uruchamiamy aplikację na porcie zewnętrznym dostarczonym przez Render
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]

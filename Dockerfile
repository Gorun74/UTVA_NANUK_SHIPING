FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Railway injects $PORT; fall back to 8000 locally
CMD gunicorn --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 120 wsgi:app

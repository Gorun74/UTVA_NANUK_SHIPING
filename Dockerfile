FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Shell form CMD so ${PORT:-8000} is expanded by /bin/sh
CMD gunicorn --bind 0.0.0.0:${PORT:-8000} --workers 1 --preload --timeout 120 wsgi:app

# One image definition for both services; SERVICE picks the app directory.
#   docker build --build-arg SERVICE=checkout -f services/Dockerfile services
FROM python:3.12-slim

ARG SERVICE
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY common/ ./
COPY ${SERVICE}/ ./

ENV PYTHONUNBUFFERED=1
CMD ["python", "app.py"]

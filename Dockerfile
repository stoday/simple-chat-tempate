FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SIMPLECHAT_DB_PATH=/app/data/simplechat.db \
    CHAT_UPLOAD_ROOT=/app/data/chat_uploads \
    RAG_UPLOAD_ROOT=/app/data/rag_files

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/backend/requirements.txt

COPY . /app

RUN mkdir -p /app/data/chat_uploads /app/data/rag_files

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

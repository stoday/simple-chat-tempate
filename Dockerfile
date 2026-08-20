FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SIMPLECHAT_DB_PATH=/app/data/simplechat.db \
    CHAT_UPLOAD_ROOT=/app/data/chat_uploads \
    RAG_UPLOAD_ROOT=/app/data/rag_files

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        unixodbc \
    && curl -sSL -O https://packages.microsoft.com/config/debian/$(. /etc/os-release && echo ${VERSION_ID%%.*})/packages-microsoft-prod.deb \
    && dpkg -i packages-microsoft-prod.deb \
    && rm packages-microsoft-prod.deb \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && apt-get purge -y --auto-remove curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/backend/requirements.txt

COPY . /app

RUN mkdir -p /app/data/chat_uploads /app/data/rag_files

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

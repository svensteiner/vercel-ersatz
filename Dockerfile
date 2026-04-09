# Ersatz Deploy Server - Production Image
FROM python:3.12-slim

# System Dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    gnupg \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Node.js installieren (für JS-Projekte)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# pnpm installieren
RUN npm install -g pnpm

# Arbeitsverzeichnis
WORKDIR /app

# Python Dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Anwendung kopieren
COPY deploy-server/ ./deploy-server/
COPY builders/ ./builders/
COPY proxy/ ./proxy/
COPY cli/ ./cli/

# Verzeichnisse erstellen
RUN mkdir -p /var/ersatz/deployments \
    /var/ersatz/repos \
    /var/ersatz/logs \
    /var/ersatz/caddy

# Umgebungsvariablen
ENV ERSATZ_BASE_DIR=/var/ersatz
ENV PYTHONUNBUFFERED=1

# Port
EXPOSE 9000

# Start
CMD ["python", "deploy-server/main.py"]

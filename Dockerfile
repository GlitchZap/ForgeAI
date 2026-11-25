# Hugging Face Spaces (Docker SDK) or Render. Serves the UI + API on $PORT (default 7860).
# Without a reachable Ollama (OLLAMA_HOST) the app opens committed runs read-only.
FROM node:24-slim AS web
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY forgeai/ forgeai/
COPY demos/ demos/
COPY holdout/ holdout/
COPY runs/ runs/
COPY --from=web /web/dist web/dist
RUN useradd -m app && chown -R app /app
USER app
ENV PORT=7860
# public host: browse committed runs only; unset to allow runs/chat when OLLAMA_HOST points at your own server
ENV FORGE_READONLY=1
EXPOSE 7860
CMD ["sh", "-c", "python -m forgeai serve --host 0.0.0.0 --port ${PORT}"]

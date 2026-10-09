# Polygraph: web app + API in one container.
# Runs on Hugging Face Spaces (Docker SDK, free CPU tier), Nebius Serverless Endpoints, or any container host.

FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.12-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    POLYGRAPH_WORKDIR=/tmp/polygraph \
    POLYGRAPH_EXECUTOR=local \
    POLYGRAPH_BUDGET_USD=10 \
    POLYGRAPH_DAILY_BUDGET_USD=1.5 \
    POLYGRAPH_RUN_BUDGET_USD=0.25 \
    POLYGRAPH_RUNS_PER_HOUR=3 \
    POLYGRAPH_RUNS_PER_DAY=6 \
    POLYGRAPH_GLOBAL_RUNS_PER_DAY=25 \
    POLYGRAPH_MAX_CONCURRENT_RUNS=2 \
    POLYGRAPH_TAVILY_DAILY_CREDITS=20

RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/* \
    && pip install uv==0.5.11 pytest==8.3.4

# Hugging Face Spaces runs containers as uid 1000.
RUN useradd -m -u 1000 polygraph
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY polygraph/ polygraph/
RUN pip install .
COPY scenarios/ scenarios/
COPY recorded/ recorded/
COPY --from=web /web/dist web/dist
RUN chown -R polygraph /app
USER polygraph

EXPOSE 7860
CMD ["python", "-m", "uvicorn", "polygraph.server:app", "--host", "0.0.0.0", "--port", "7860", "--proxy-headers", "--forwarded-allow-ips", "*"]

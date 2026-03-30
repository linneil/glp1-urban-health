# Multi-stage build: builder installs dependencies, runtime runs the app
# This keeps the final image small (~250 MB vs ~800 MB)

# --------------- Stage 1: Builder ---------------
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

# Install dependencies into an isolated venv
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml .
# Create a minimal setup so pip can resolve the [project] table
RUN mkdir -p src && \
    pip install --upgrade pip && \
    pip install .

# --------------- Stage 2: Runtime ---------------
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Copy venv from builder (all dependencies pre-installed)
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Copy project source code
COPY src/ src/
COPY pipelines/ pipelines/
COPY dashboard/ dashboard/
COPY data/ data/

# Expose Streamlit default port
EXPOSE 8501

# Health check using curl (available in slim image)
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1

# Default: launch the dashboard
# To run the pipeline instead: docker run glp1-dashboard python pipelines/run_pipeline.py
CMD ["streamlit", "run", "dashboard/app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--browser.gatherUsageStats=false"]

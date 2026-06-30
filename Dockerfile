# GovTech Citizen Chatbot — multi-stage Docker image
# Python 3.12, minimal footprint, non-root user.

FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies
RUN pip install --upgrade pip

COPY requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /wheels -r requirements.txt


FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="GovTech Citizen Chatbot"
LABEL org.opencontainers.image.description="FastAPI framework for WhatsApp/Chatwoot AI chatbots"
LABEL org.opencontainers.image.licenses="MIT"

# Create non-root user
RUN addgroup --system chatbot && adduser --system --ingroup chatbot chatbot

WORKDIR /app

# Install wheels built in the previous stage
COPY --from=builder /wheels /wheels
RUN pip install --no-cache /wheels/*

# Copy application code
COPY app/ ./app/
COPY agents/ ./agents/

# Change ownership
RUN chown -R chatbot:chatbot /app

USER chatbot

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

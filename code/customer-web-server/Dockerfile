# Customer Web Server Dockerfile
# Multi-stage build: test and production targets

# ============ Base Stage ============
FROM python:3.11-slim AS base

WORKDIR /app

COPY requirements.txt .

# Create non-root user for security
RUN useradd -m appuser

EXPOSE 5000

# ============ Production Stage ============
FROM base AS production

# Install only production dependencies (exclude pytest)
RUN grep -v "pytest" requirements.txt > requirements-prod.txt && \
    pip install --no-cache-dir -r requirements-prod.txt

# Copy only application code (no tests)
COPY app.py .

RUN chown -R appuser:appuser /app
USER appuser

CMD ["python", "app.py"]

# ============ Test Stage ============
FROM base AS test

# Install all dependencies including pytest
RUN pip install --no-cache-dir -r requirements.txt

# Copy everything including tests
COPY . .

RUN chown -R appuser:appuser /app
USER appuser

CMD ["pytest", "tests/", "-v"]

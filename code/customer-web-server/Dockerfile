# Customer Web Server Dockerfile
# Builds a lightweight Python image for the customer-facing web service

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements first (for layer caching)
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user for security
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Expose the Flask port
EXPOSE 5000

# Run the application
CMD ["python", "app.py"]

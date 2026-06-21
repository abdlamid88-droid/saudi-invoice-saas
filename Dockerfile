# Use official python slim image
FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Upgrade pip and install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
    streamlit \
    mcp \
    psycopg2-binary \
    fpdf2 \
    arabic-reshaper \
    python-bidi \
    google-generativeai \
    qrcode[pil] \
    lxml \
    cryptography

# Copy the application code
COPY . .

# Expose Streamlit default port
EXPOSE 8501

# Command to run the Streamlit dashboard
CMD ["streamlit", "run", "zatca_chat.py", "--server.port=8501", "--server.address=0.0.0.0"]

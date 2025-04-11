FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc build-essential && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements_docker.txt requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn

# Copy the application code
COPY *.py ./

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=5000

# Create a non-root user to run the app
RUN useradd -m appuser
USER appuser

# Expose the port the app runs on
EXPOSE 5000

# Start the application with Gunicorn
CMD gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120 main:app
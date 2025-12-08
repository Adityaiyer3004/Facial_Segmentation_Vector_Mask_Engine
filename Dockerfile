# Dockerfile

FROM python:3.11-slim

# Work directory inside container
WORKDIR /app

# Python runtime sanity
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# System deps for OpenCV etc.
RUN apt-get update && apt-get install -y \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
  && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the backend
COPY . .

# Expose FastAPI port
EXPOSE 8000

# Launch FastAPI (change app.main:app if your entrypoint is different)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

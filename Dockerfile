FROM python:3.11-slim

# set working directory
WORKDIR /app

# install system deps (optional but safe)
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# copy requirements first (cache friendly)
COPY requirements.txt .

# install python deps
RUN pip install --no-cache-dir -r requirements.txt

# copy project files
COPY . .

# expose port (Railway will set PORT env)
EXPOSE 8080

# run app with gunicorn
CMD ["gunicorn", "verify_app:app", "--bind", "0.0.0.0:$PORT"]

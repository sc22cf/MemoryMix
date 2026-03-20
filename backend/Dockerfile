FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ .

# Copy the mood dataset CSV so ingestion can run during the build
COPY muse_v3.csv .

# Ensure uploads directory exists
RUN mkdir -p uploads

# Ensure data directory exists for the SQLite runtime database
RUN mkdir -p data

# Pre-build the mood_songs database from the CSV (baked into the image)
RUN python -m services.mood_matching.ingest_csv_to_db

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

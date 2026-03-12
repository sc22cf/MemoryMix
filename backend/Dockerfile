FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (includes services/mood_songs.db)
COPY . .

# Ensure uploads directory exists
RUN mkdir -p uploads

# Ensure data directory exists for the SQLite runtime database
RUN mkdir -p data

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

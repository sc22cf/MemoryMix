#!/bin/bash

echo "Resetting database and uploads..."

# Remove local dev database and uploads (if running outside Docker)
rm -f backend/memorymix.db
rm -f data/memorymix.db
rm -rf backend/uploads/*
mkdir -p backend/uploads

# Tear down containers and remove named volumes (db_data, uploads_data)
docker compose down -v

# Rebuild and start fresh
docker compose up --build

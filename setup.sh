#!/bin/bash

# Memory Mix Setup Script

echo "🎵 Memory Mix Setup 🎵"
echo "====================="
echo ""

# Check Python
echo "Checking Python..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.10+"
    exit 1
fi
echo "✅ Python found"

# Check Node.js
echo "Checking Node.js..."
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed. Please install Node.js 18+"
    exit 1
fi
echo "✅ Node.js found"

# Backend setup
echo ""
echo "Setting up backend..."
cd backend

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "Installing Python dependencies..."
pip install -r requirements.txt

# Create .env if it doesn't exist
if [ ! -f ".env" ]; then
    echo "Creating .env file..."
    cp .env.example .env
    echo "⚠️  Please update backend/.env with your API credentials"
fi

cd ..

# Frontend setup
echo ""
echo "Setting up frontend..."
cd frontend

# Install dependencies
echo "Installing Node.js dependencies..."
npm install

# Create .env.local if it doesn't exist
if [ ! -f ".env.local" ]; then
    echo "Creating .env.local file..."
    cp .env.local.example .env.local
    echo "⚠️  Please update frontend/.env.local with your API credentials"
fi

cd ..

echo ""
echo "✨ Setup complete! ✨"
echo ""
echo "Next steps:"
echo "1. Configure backend/.env with your Spotify and Google API credentials"
echo "2. Configure frontend/.env.local with your client IDs"
echo ""
echo "To start the backend:"
echo "  cd backend"
echo "  source venv/bin/activate"
echo "  uvicorn main:app --reload"
echo ""
echo "To start the frontend (in a new terminal):"
echo "  cd frontend"
echo "  npm run dev"
echo ""
echo "Visit http://localhost:3000 to start using Memory Mix!"

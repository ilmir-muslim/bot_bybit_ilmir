#!/bin/bash
echo ">> Creating tables (if not exist)..."
python -m init_db

echo ">> Starting app..."
exec uvicorn main:app --host 0.0.0.0 --port 8000

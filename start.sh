#!/bin/bash

if [ "$SERVICE_TYPE" = "advisor" ]; then
    python advisor_bot/main.py
else
    PYTHONPATH=/app/backend uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT
fi

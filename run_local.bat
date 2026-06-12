@echo off
REM ==========================================================================
REM Run the Nexus workbench on a LOCAL workstation (Windows).
REM Everything runs on localhost - no RunPod, no SSH tunnel.
REM
REM   Double-click run_local.bat  (or run it from a terminal)
REM
REM Then open http://localhost:8501 in a browser on this machine.
REM Prerequisite: Ollama for Windows installed (https://ollama.com/download).
REM ==========================================================================
cd /d "%~dp0"

if "%CHROMA_DB_DIR%"=="" set CHROMA_DB_DIR=.\chroma_db

echo [1/4] Ensuring Ollama is running...
curl -sf http://localhost:11434/api/tags >nul 2>&1 || start "" ollama serve
timeout /t 4 >nul

echo [2/4] Ensuring models are present (downloads once)...
ollama pull qwen2.5vl:7b
ollama pull qwen2.5:72b
ollama pull qwq:32b
ollama pull bge-m3

echo [3/4] Ensuring ChromaDB is running...
curl -sf http://localhost:8000/api/v2/heartbeat >nul 2>&1 || start "" chroma run --host localhost --port 8000 --path "%CHROMA_DB_DIR%"
timeout /t 4 >nul

echo [4/4] Starting the app on http://localhost:8501 ...
streamlit run app.py --server.port 8501

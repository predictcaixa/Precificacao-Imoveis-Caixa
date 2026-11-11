#!/bin/bash
# ================================================================
# ImóvelML — Script de inicialização completo
# ================================================================
# Uso: bash start.sh
# ================================================================

set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

echo ""
echo -e "${BOLD}${BLUE}╔══════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${BLUE}║       ImóvelML — Sistema de Precificação     ║${NC}"
echo -e "${BOLD}${BLUE}║           Machine Learning + FastAPI         ║${NC}"
echo -e "${BOLD}${BLUE}╚══════════════════════════════════════════════╝${NC}"
echo ""

# Detectar python
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo -e "${RED}[ERRO] Python não encontrado. Instale Python 3.9+${NC}"
    exit 1
fi

echo -e "${GREEN}[1/4] Python encontrado: $($PYTHON --version)${NC}"

# Instalar dependências
echo -e "${YELLOW}[2/4] Instalando dependências...${NC}"
cd backend
pip install -r requirements.txt -q

# Treinar modelos (se não existirem)
if [ ! -f "models/metadata.json" ]; then
    echo -e "${YELLOW}[3/4] Treinando modelos (primeira execução)...${NC}"
    $PYTHON app/train_model.py
else
    echo -e "${GREEN}[3/4] Modelos já treinados (pulando). Delete /models para retreinar.${NC}"
fi

# Iniciar API
echo -e "${YELLOW}[4/4] Iniciando API FastAPI...${NC}"
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  API REST:   http://localhost:8001           ║${NC}"
echo -e "${GREEN}║  Swagger UI: http://localhost:8001/docs      ║${NC}"
echo -e "${GREEN}║  Frontend:   abrir frontend/index.html       ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
echo ""

uvicorn app.main:app --reload --port 8001 --host 0.0.0.0

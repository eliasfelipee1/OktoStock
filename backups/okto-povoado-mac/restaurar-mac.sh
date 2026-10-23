#!/bin/bash
# Restaura o banco de demonstracao do OktoStock no macOS (PostgreSQL via Homebrew).
set -euo pipefail
cd "$(dirname "$0")"
command -v psql >/dev/null || { echo "psql nao encontrado. Instale: brew install postgresql@16 && brew services start postgresql@16"; exit 1; }
shasum -a 256 -c SHA256SUMS
DB="${1:-okto}"
createdb "$DB"
psql -v ON_ERROR_STOP=1 --single-transaction -q -d "$DB" -f okto.sql
echo "Pronto. Banco '$DB' restaurado."
echo "No .env: DATABASE_URL=postgresql://$(whoami)@127.0.0.1:5432/$DB"
echo "         LOCAL_DEMO_OPERATION_ID=$(sed 's/.*=//' operacao.txt)"

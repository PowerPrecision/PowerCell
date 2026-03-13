#!/bin/bash
# Script para mudar entre ambiente de desenvolvimento e produção

ENV_FILE="/app/backend/.env"

case "$1" in
    prod|production)
        echo "🚀 Mudando para PRODUÇÃO..."
        sed -i 's/DB_NAME="powercell_dev"/DB_NAME="powercell"/' "$ENV_FILE"
        echo "✅ DB_NAME alterado para 'powercell'"
        ;;
    dev|development)
        echo "🔧 Mudando para DESENVOLVIMENTO..."
        sed -i 's/DB_NAME="powercell"/DB_NAME="powercell_dev"/' "$ENV_FILE"
        echo "✅ DB_NAME alterado para 'powercell_dev'"
        ;;
    status)
        echo "📊 Configuração atual:"
        grep "DB_NAME" "$ENV_FILE"
        ;;
    *)
        echo "Uso: $0 {prod|dev|status}"
        echo ""
        echo "Exemplos:"
        echo "  $0 prod    - Muda para base de dados de produção"
        echo "  $0 dev     - Muda para base de dados de desenvolvimento"
        echo "  $0 status  - Mostra configuração atual"
        exit 1
        ;;
esac

#!/bin/bash
# CreditoIMO Test Runner
# Runs both API and E2E tests

set -e

echo "================================================"
echo "🧪 CreditoIMO Test Suite"
echo "================================================"
echo ""

cd /app/backend

echo "📡 Running Backend API Tests (37 tests)..."
echo "------------------------------------------------"
python -m pytest tests/test_*.py -v --ignore=tests/e2e --tb=short

echo ""
echo "🌐 Running Frontend E2E Tests (17 tests)..."
echo "------------------------------------------------"
python -m pytest tests/e2e/ -v --tb=short

echo ""
echo "================================================"
echo "✅ All tests completed successfully!"
echo "================================================"

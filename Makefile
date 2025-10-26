.PHONY: install shell test test-integration clean format lint

# ============================================================================
# PYTHON/POETRY COMMANDS
# ============================================================================

install:
	@echo "📦 Installing dependencies with Poetry..."
	poetry install
	@echo "✅ Dependencies installed!"

shell:
	@echo "🐚 Starting Poetry shell..."
	poetry shell

env:
	@echo "🔧 Activating virtual environment..."
	@poetry shell

# ============================================================================
# TESTING COMMANDS
# ============================================================================

test-integration:
	@echo "🧪 Running integration tests..."
	@echo "📋 Loading environment variables from .env..."
	poetry run python examples/test_with_sdk.py

test-quick:
	@echo "⚡ Running quick integration test..."
	poetry run python examples/test_integration.py $(WEBHOOK_URL)

test: test-integration

# ============================================================================
# DEVELOPMENT COMMANDS
# ============================================================================

format:
	@echo "🎨 Formatting code with black..."
	poetry run black ezthrottle/ examples/ tests/

lint:
	@echo "🔍 Linting code with ruff..."
	poetry run ruff check ezthrottle/ examples/ tests/

clean:
	@echo "🧹 Cleaning up..."
	rm -rf build/ dist/ *.egg-info .pytest_cache __pycache__
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	@echo "✅ Cleaned!"

# ============================================================================
# USAGE EXAMPLES
# ============================================================================

help:
	@echo "EZThrottle Python SDK - Make Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install          Install dependencies with Poetry"
	@echo "  make shell            Start Poetry shell (interactive)"
	@echo ""
	@echo "Testing:"
	@echo "  make test             Run full integration test suite"
	@echo "  make test-integration Run test_with_sdk.py"
	@echo "  make test-quick       Run quick test (requires WEBHOOK_URL)"
	@echo ""
	@echo "Development:"
	@echo "  make format           Format code with black"
	@echo "  make lint             Lint code with ruff"
	@echo "  make clean            Clean up build artifacts"
	@echo ""
	@echo "Example workflow:"
	@echo "  1. make install       # Install dependencies"
	@echo "  2. cp .env.example .env && vim .env  # Configure"
	@echo "  3. make test          # Run tests"

.PHONY: integration deploy test teardown clean help secrets

# Variables
APP_NAME := ezthrottle-sdk-py
APP_URL := https://$(APP_NAME).fly.dev

help:
	@echo "EZThrottle Python SDK Integration Tests"
	@echo ""
	@echo "Usage:"
	@echo "  make integration  # Deploy → Test → Teardown (run on every push)"
	@echo ""
	@echo "Individual targets:"
	@echo "  make secrets     # Set Fly secrets from .env.test"
	@echo "  make deploy      # Deploy app to Fly"
	@echo "  make test        # Run hurl tests"
	@echo "  make teardown    # Destroy Fly app"

secrets:
	@echo "🔒 Setting Fly secrets..."
	@if [ ! -f .env.test ]; then \
		echo "❌ Error: .env.test not found!"; \
		exit 1; \
	fi
	@bash .env.test
	@echo "✅ Secrets set"

# ONE COMMAND: Deploy → Test → Teardown (only if tests pass)
integration:
	@echo "🚀 Starting integration test cycle..."
	@echo ""

	@# Step 1: Deploy
	@echo "📦 STEP 1/3: Deploying to Fly..."
	@$(MAKE) deploy
	@echo ""

	@# Step 2: Test (if this fails, don't teardown)
	@echo "🧪 STEP 2/3: Running integration tests..."
	@$(MAKE) test || (echo "❌ Tests failed! App left running for debugging: $(APP_URL)" && exit 1)
	@echo ""

	@# Step 3: Teardown (only runs if tests passed)
	@echo "🗑️  STEP 3/3: Tests passed! Tearing down..."
	@$(MAKE) teardown
	@echo ""
	@echo "✅ Integration cycle complete!"

deploy:
	@echo "   Creating Fly app (if needed)..."
	@fly apps create $(APP_NAME) --org ezthrottle 2>/dev/null || true

	@echo "   Setting secrets..."
	@$(MAKE) secrets

	@echo "   Deploying to Fly..."
	@cd .. && fly deploy \
		--config test-app/fly.toml \
		--dockerfile test-app/Dockerfile \
		--app $(APP_NAME) \
		--ha=false

	@echo "   Waiting for deployment..."
	@sleep 10
	@echo "✅ Deployed: $(APP_URL)"

test:
	@echo "   Resetting webhooks..."
	@curl -X POST $(APP_URL)/webhooks/reset -s > /dev/null
	@echo "   Running hurl tests..."
	@hurl --test \
		--variable TEST_APP_URL=$(APP_URL) \
		--color \
		tests/*.hurl
	@echo "✅ All tests passed"

teardown:
	@fly apps destroy $(APP_NAME) --yes 2>/dev/null || true
	@echo "✅ Teardown complete"

clean:
	@curl -X POST $(APP_URL)/webhooks/reset
	@echo "✅ Webhooks cleared"

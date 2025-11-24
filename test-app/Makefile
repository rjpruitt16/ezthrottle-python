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
	@if [ -f .env.test ]; then \
		fly secrets set --app $(APP_NAME) $$(grep -v '^#' .env.test | grep -v '^$$' | xargs) 2>/dev/null || echo "⚠️  Could not set secrets (app may not exist yet)"; \
	else \
		echo "⚠️  No .env.test file, assuming secrets already set"; \
	fi
	@echo "✅ Secrets set (or skipped)"

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

	@# Step 3: Scale to zero (keeps app but costs nothing)
	@echo "🔻 Scaling app to zero..."
	@$(MAKE) teardown
	@echo "✅ Integration tests complete! App scaled to zero (no cost)"

deploy:
	@echo "   Listing Fly organizations..."
	@fly orgs list || echo "⚠️  Could not list orgs"

	@echo "   Listing Fly apps..."
	@fly apps list || echo "⚠️  Could not list apps"

	@echo "   Creating Fly app (if needed)..."
	@fly apps create $(APP_NAME) --org ezthrottle 2>&1 || echo "⚠️  App create failed (might already exist)"

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
	@fly scale count 0 --app $(APP_NAME) --yes 2>&1 || echo "⚠️  Scale to zero failed (app might not exist)"
	@echo "✅ App scaled to zero (costs nothing when idle)"

clean:
	@curl -X POST $(APP_URL)/webhooks/reset
	@echo "✅ Webhooks cleared"

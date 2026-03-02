.PHONY: help test test-js test-verbose test-coverage test-fast test-watch test-specific clean install lint lint-strict mypy check quick-check format run

# Default Python command
PYTHON := python3

# Default target
.DEFAULT_GOAL := help

help: ## Show this help message
	@echo "SpendSense - Development Commands"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install all dependencies
	$(PYTHON) -m pip install -r requirements.txt

test: ## Run all tests (Python + JS)
	$(PYTHON) -m pytest tests/ -v
	npx vitest run

test-js: ## Run JS unit tests (FetcherEngine, parseAmount, etc.)
	npx vitest run

test-coverage: ## Run tests with coverage report (minimum 70%)
	$(PYTHON) -m pytest tests/ --cov=domain --cov=application --cov=infrastructure --cov=presentation --cov-report=html --cov-report=term --cov-report=xml --cov-fail-under=70

test-specific: ## Run specific test file (usage: make test-specific FILE=test_classifier.py)
	$(PYTHON) -m pytest tests/$(FILE) -v

test-llm: ## Run LLM integration tests (requires GEMINI_API_KEY, expensive)
	@echo "⚠️  Running LLM tests - this will make API calls and may incur costs"
	$(PYTHON) -m pytest -m llm -v

test-all: ## Run ALL tests including expensive LLM tests
	@echo "⚠️  Running all tests including LLM tests - this may incur costs"
	$(PYTHON) -m pytest -m "" -v

lint: ## Run linting checks with score threshold (CI-friendly)
	$(PYTHON) -m pip install pylint
	@echo "Disabled codes explanation:"
	@echo "  C0111,C0103: Documentation/naming conventions"
	@echo "  R0903,R0913,R0917: Design patterns (dataclasses, rich domain entities)"
	@echo "  W0107: Unnecessary pass in abstract methods (ABC pattern)"
	@echo "  W1203: F-string in logging (readability over micro-optimization)"
	@echo "  W0718: Broad-exception-caught (intentional fallback patterns)"
	@echo "  R0801: Duplicate-code (acceptable in blueprints with similar CRUD patterns)"
	@echo "  R0914,R0902,R0911,R0912,R0915: Complexity metrics (tracked separately, not blocking)"
	@echo ""
	$(PYTHON) -m pylint domain/ application/ infrastructure/ presentation/ \
		--disable=C0111,C0103,R0903,R0913,W0107,W1203,W0718,R0801,R0914,R0917,R0902,R0911,R0912,R0915 \
		--fail-under=9.5

lint-strict: ## Run linting checks without score threshold (shows all issues)
	$(PYTHON) -m pip install pylint
	$(PYTHON) -m pylint domain/ application/ infrastructure/ presentation/ \
		--disable=C0111,C0103,R0903,R0913,W0107,W1203,W0718,R0801,R0914,R0917,R0902,R0911,R0912,R0915

mypy: ## Run mypy type checker
	@echo "Running mypy type checker..."
	$(PYTHON) -m pip install mypy
	$(PYTHON) -m mypy presentation/ infrastructure/ application/ domain/

check: test mypy lint ## Run tests, mypy, and lint (recommended before commit)

quick-check: test-fast mypy lint ## Fast tests, mypy, and lint

test-fast: ## Run tests and stop on first failure
	$(PYTHON) -m pytest tests/ -v -x

format: ## Format code with black (requires black)
	$(PYTHON) -m pip install black
	$(PYTHON) -m black domain/ application/ infrastructure/ presentation/ tests/

run: ## Run the Flask application (development mode)
	$(PYTHON) -m presentation.web.app

run-prod: ## Run the Flask application (production mode with gunicorn)
	gunicorn -w 4 -b 0.0.0.0:5000 presentation.web.app:app

db-backup: ## Backup the database
	@mkdir -p backups
	@cp data/transactions.db backups/transactions_backup_$$(date +%Y%m%d_%H%M%S).db
	@echo "✓ Database backed up to backups/"

# Development workflow shortcuts
dev: install ## Setup development environment
	@echo ""
	@echo "✓ Development environment ready!"
	@echo ""
	@echo "Next steps:"
	@echo "  • make test          - Run tests"
	@echo "  • make run           - Start Flask app"
	@echo "  • make help          - See all commands"

# Statistics
stats: ## Show code statistics
	@echo "Code Statistics:"
	@echo "=================="
	@echo -n "Python files: "
	@find . -name "*.py" -not -path "./.venv/*" -not -path "./venv/*" | wc -l
	@echo -n "Lines of code: "
	@find . -name "*.py" -not -path "./.venv/*" -not -path "./venv/*" -exec cat {} \; | wc -l
	@echo -n "Test files: "
	@find tests/ -name "test_*.py" 2>/dev/null | wc -l || echo "0"

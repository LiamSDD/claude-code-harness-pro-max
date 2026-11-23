PY ?= python3

.PHONY: test lint format coverage build check clean

test:
	$(PY) -m unittest discover -s tests -q

lint:
	ruff check src tests
	ruff format --check src tests

format:
	ruff format src tests
	ruff check --fix src tests

coverage:
	coverage run -m unittest discover -s tests -q && coverage report

build:
	$(PY) -m build

# Everything CI runs, locally.
check: lint test
	./bin/harness policy validate
	./bin/harness scan --high-only src hooks .claude-plugin

clean:
	rm -rf build dist *.egg-info .coverage htmlcov .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

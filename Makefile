.PHONY: test-core test-dataframe test-end_to_end test-export test-rocrate test-s3 test-all format format-diff

test-core:
	uv pip install -e ".[core, test-core]"
	uv run pytest tests/adapters tests/core -m core --disable-warnings
	uv run pytest tests/adapters tests/core -m session --disable-warnings

test-dataframe:
	uv pip install -e ".[dataframe-adapter, test-core]"
	uv run pytest -s -vv tests/adapters tests/core/interfaces -m dataframe --disable-warnings
	uv run pytest -s -vv tests/core -m dataframe --disable-warnings

test-end_to_end:
	uv pip install -e ".[dataframe-adapter, export-adapter, test-core]"
	uv run pytest tests/end_to_end -m end_to_end --disable-warnings

test-export:
	uv pip install -e ".[export-adapter, test-core]"
	uv run pytest tests/adapters tests/core -m export --disable-warnings

test-rocrate:
	uv pip install -e ".[rocrate-adapter, test-core]"
	uv run pytest tests/adapters tests/core -m rocrate -W ignore

test-s3:
	uv pip install -e ".[s3-adapter, test-core]"
	uv run pytest tests/adapters tests/core -m s3 -W ignore

test-all: test-core test-dataframe test-end_to_end test-export test-s3

format:
	uv pip install ruff
	uv run ruff format .

format-diff:
	uv pip install ruff
	uv run ruff format . --diff

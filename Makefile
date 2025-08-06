.PHONY: test-core test-dataframe test-export test-rocrate test-all format

test-core:
	uv pip install -e ".[core, test-core]"
	uv run pytest tests -m core --disable-warnings

test-dataframe:
	uv pip install -e ".[dataframe-adapter, test-core]"
	uv run pytest -s -vv tests/adapters tests/core/interfaces -m dataframe --disable-warnings

test-export:
	uv pip install -e ".[export-adapter, test-core]"
	uv run pytest -m export --disable-warnings

test-rocrate:
	uv pip install -e ".[rocrate-adapter, test-core]"
	uv run pytest -m rocrate -W ignore

test-s3:
	uv pip install -e ".[s3-adapter, test-core]"
	uv run pytest -m s3 -W ignore

test-all: test-core test-dataframe test-export test-s3

format:
	uv pip install ruff
	uv run ruff format .
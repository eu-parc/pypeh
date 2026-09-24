.PHONY: test-core test-dataframe test-end_to_end test-end_to_end_consistency test-export test-rocrate test-s3 test-compehndly test-all docs docs-serve format format-diff

test-core:
	uv pip install -e ".[core, test-core]"
	uv run pytest -s tests/adapters tests/core -m core --disable-warnings 
	uv run pytest -s tests/adapters tests/core -m session --disable-warnings

test-dataframe:
	uv pip install -e ".[dataframe-adapter, test-core, test-dataframe]"
	uv run pytest -s -vv tests/adapters tests/core/interfaces -m dataframe --disable-warnings
	uv run pytest -s -vv tests/core -m dataframe --disable-warnings

test-end_to_end:
	uv pip install -e ".[dataframe-adapter, export-adapter, test-core]"
	uv run pytest -s tests/end_to_end -m end_to_end --disable-warnings

test-end_to_end_consistency:
	uv pip install -e ".[dataframe-adapter, export-adapter, test-core]"
	uv run pytest tests/end_to_end -m end_to_end_consistency --disable-warnings

test-rocrate:
	uv pip install -e ".[rocrate-adapter, test-core]"
	uv run pytest -s tests/adapters tests/core -m rocrate -W ignore

test-s3:
	uv pip install -e ".[s3-adapter, dataframe-adapter, test-core, test-s3]"
	uv run pytest -s tests/adapters tests/core tests/integration -m s3 -W ignore

test-compehndly:
	uv pip install -e ".[dataframe-adapter, test-core, compehndly]"
	uv run pytest -s tests/end_to_end -m compehndly -W ignore

test-xlsx:
	uv pip install -e ".[dataframe-adapter, test-core, test-dataframe, xlsxwriter]"
	uv run pytest -s -vv tests/adapters -m xlsx --disable-warnings
	uv run pytest -s -vv tests/core -m xlsx --disable-warnings

test-all: test-core test-dataframe test-end_to_end test-end_to_end_consistency test-s3 test-compehndly

docs:
	uv run --group docs mkdocs build --strict

docs-serve:
	uv run --group docs mkdocs serve

# Always use the ruff version pinned in the `dev` dependency group so that
# local formatting matches what CI checks. Do not `uv pip install ruff`:
# an unpinned ruff reformats differently from the pinned one.
format:
	uv run --group dev ruff format .

format-diff:
	uv run --group dev ruff format . --diff

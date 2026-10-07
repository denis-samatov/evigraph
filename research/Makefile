.PHONY: dev lint test data download prepare cellar dedup splits graph baseline all

ARCHIVE := data/raw/multi_eurlex.tar.gz
ARCHIVE_URL := https://huggingface.co/datasets/coastalcph/multi_eurlex/resolve/main/data/multi_eurlex.tar.gz

dev:
	uv sync --all-groups

lint:
	uv run ruff check src tests && uv run ruff format --check src tests

test:
	uv run pytest -q

download: $(ARCHIVE)
$(ARCHIVE):
	mkdir -p data/raw
	curl -sSL --retry 5 -C - -o $@ $(ARCHIVE_URL)

prepare: download
	uv run evigraph-research prepare

cellar:
	uv run evigraph-research cellar

dedup:
	uv run evigraph-research dedup

splits:
	uv run evigraph-research splits

graph:
	uv run evigraph-research graph-report

baseline:
	uv run evigraph-research baseline

all: prepare cellar dedup splits graph baseline

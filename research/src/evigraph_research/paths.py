"""Filesystem layout of the research workspace."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW = DATA / "raw"
INTERIM = DATA / "interim"
CACHE = DATA / "cache"
REPORTS = ROOT / "reports"

RAW_ARCHIVE = RAW / "multi_eurlex.tar.gz"
# sha256 of the Git LFS object coastalcph/multi_eurlex:data/multi_eurlex.tar.gz
RAW_ARCHIVE_SHA256 = "3a2195bc01c7aea0e302bc7af94f2f55f0c15cdeabfe4e086c083196069a2e83"

CORPUS = INTERIM / "corpus_en.parquet"
LABELS = INTERIM / "labels.json"
CELLAR_EDGES = INTERIM / "cellar_edges.parquet"
CELLAR_META = INTERIM / "cellar_meta.parquet"
DUPLICATES = INTERIM / "duplicates.parquet"
SPLITS = INTERIM / "split_manifest.parquet"


def ensure_dirs() -> None:
    for d in (RAW, INTERIM, CACHE, REPORTS):
        d.mkdir(parents=True, exist_ok=True)


# predictions of the strong text control (strong.py), aligned to model_dev+calib_fit+risk_cert rows
STRONG_PREDS = CACHE / "preds" / "p_strong.joblib"

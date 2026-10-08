"""Runtime settings, read from EVIGRAPH_* environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EVIGRAPH_", extra="ignore")

    database_url: str = "postgresql+psycopg://evigraph@127.0.0.1:54329/evigraph"
    artifact_dir: Path = Path("artifacts")

    # Provenance: near-duplicate detection (word 5-gram MinHash, 128 permutations, LSH).
    minhash_perm: int = 128
    minhash_bands: int = 32  # 32 bands x 4 rows: candidate pairs from Jaccard ~0.5 upwards
    near_duplicate_threshold: float = 0.8

    # Engine
    knn_k: int = 20
    knn_candidates: int = 200
    min_positives_for_text_model: int = 5
    stacker_folds: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()

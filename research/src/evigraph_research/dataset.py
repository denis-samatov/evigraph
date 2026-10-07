"""Load the corpus, the split manifest and the level-2 label matrix in one aligned frame."""

from dataclasses import dataclass

import numpy as np
import orjson
import pandas as pd

from evigraph_research import paths

SPLIT_ORDER = ("train", "model_dev", "calib_fit", "risk_cert", "final_test")


@dataclass
class Dataset:
    frame: pd.DataFrame  # celex_id, publication_date, split, flags (+ text if requested)
    labels: list[str]
    y: np.ndarray  # (n_docs, n_labels) bool, level-2 EuroVoc

    def mask(self, *splits: str) -> np.ndarray:
        return self.frame["split"].isin(splits).to_numpy()


def load(*, with_text: bool = False) -> Dataset:
    cols = ["celex_id", "labels_level_2"] + (["text"] if with_text else [])
    corpus = pd.read_parquet(paths.CORPUS, columns=cols)
    manifest = pd.read_parquet(paths.SPLITS)
    frame = manifest.merge(corpus, on="celex_id", how="inner", validate="one_to_one")
    if len(frame) != len(manifest):
        msg = "corpus and split manifest are out of sync"
        raise ValueError(msg)
    labels = orjson.loads(paths.LABELS.read_bytes())["level_2"]
    col = {lab: j for j, lab in enumerate(labels)}
    y = np.zeros((len(frame), len(labels)), dtype=bool)
    for i, ls in enumerate(frame["labels_level_2"]):
        y[i, [col[lab] for lab in ls]] = True
    frame = frame.drop(columns=["labels_level_2"])
    return Dataset(frame=frame, labels=labels, y=y)

"""RusLawOD (Saveliev & Kuchakov, 2024; CC BY-NC 4.0): Russian federal legislation with the
official classifier of legal acts (`classifierByIPS`, hierarchical codes such as
010.140.030.010.000, several per act).

Concepts are classifier sections at level 1 (first code segment, 21 sections) or level 2
(first two segments). Section names are mostly absent from the data, so a concept's
definition is built from the most frequent full labels found under it in the data itself.
"""

import collections
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from evigraph_core.benchmark import Doc
from evigraph_core.catalogs import ConceptSpec

CODE = re.compile(r"\d{3}(\.\d{3}){4}")
MAX_CHARS = 50_000


@dataclass
class Corpus:
    frame: pd.DataFrame  # key, date, text, codes (list[(code, label)])
    level: int

    def labels(self, row) -> frozenset[str]:
        width = 3 if self.level == 1 else 7
        return frozenset(code[:width] for code, _ in row.codes)

    def concepts(self, keys: set[str]) -> list[ConceptSpec]:
        width = 3 if self.level == 1 else 7
        names: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
        for codes in self.frame["codes"]:
            for code, label in codes:
                names[code[:width]][label] += 1
        specs = []
        for k in sorted(keys):
            top = [label for label, _ in names[k].most_common(5)]
            specs.append(
                ConceptSpec(key=k, label=top[0][:500] if top else k, definition="; ".join(top))
            )
        return specs


def _parse(raw: str) -> list[tuple[str, str]]:
    parts = [p.strip().replace("\xa0", " ").strip() for p in raw.split("$")]
    pairs = zip(parts[0::2], parts[1::2], strict=False)
    return [(code, label) for code, label in pairs if CODE.fullmatch(code)]


def load(paths: list[Path], *, level: int) -> Corpus:
    cols = ["pravogovruNd", "docdateIPS", "textIPS", "classifierByIPS"]
    df = pd.concat([pq.read_table(p, columns=cols).to_pandas() for p in paths], ignore_index=True)
    df = df[df["classifierByIPS"].notna() & df["textIPS"].notna()].copy()
    df["codes"] = df["classifierByIPS"].map(_parse)
    df = df[df["codes"].map(len) > 0]
    df["date"] = pd.to_datetime(df["docdateIPS"], format="%d.%m.%Y", errors="coerce")
    df = df[df["date"].notna()].drop_duplicates("pravogovruNd")
    df["text"] = df["textIPS"].str.strip().str.slice(0, MAX_CHARS)
    df = df.rename(columns={"pravogovruNd": "key"})[["key", "date", "text", "codes"]]
    return Corpus(df.sort_values(["date", "key"]).reset_index(drop=True), level)


def split(corpus: Corpus, *, evaluation: int, min_support: int = 20):
    """Older documents form the review pool, the newest `evaluation` documents are evaluated.
    Concepts with fewer than `min_support` documents in the pool are dropped."""
    pool = corpus.frame.iloc[: len(corpus.frame) - evaluation]
    later = corpus.frame.iloc[len(corpus.frame) - evaluation :]
    support = collections.Counter(k for r in pool.itertuples() for k in corpus.labels(r))
    keys = {k for k, n in support.items() if n >= min_support}

    def docs(frame) -> list[Doc]:
        return [Doc(r.key, r.text, corpus.labels(r) & keys) for r in frame.itertuples()]

    return docs(pool), docs(later), corpus.concepts(keys)

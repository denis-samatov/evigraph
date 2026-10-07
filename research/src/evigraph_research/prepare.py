"""Extract the English part of MultiEURLEX with all label levels into one parquet file.

Only `celex_id`, `publication_date`, the English text and the EuroVoc labels are kept.
Labels are stored separately from the text columns so that model inputs never see them.
"""

import hashlib
import tarfile
import unicodedata

import orjson
import pandas as pd

from evigraph_research import paths

OFFICIAL_SPLITS = {"train.jsonl": "train", "dev.jsonl": "dev", "test.jsonl": "test"}
LEVELS = ("level_1", "level_2", "level_3")


def sha256_file(path, chunk: int = 1 << 24) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def normalize_text(text: str) -> str:
    """Canonical text form: NFC, unified newlines, trimmed trailing spaces.

    Evidence offsets in the product are defined over this form (Unicode code points).
    """
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.split("\n")).strip()


def extract(*, verify: bool = True) -> pd.DataFrame:
    paths.ensure_dirs()
    if verify:
        digest = sha256_file(paths.RAW_ARCHIVE)
        if digest != paths.RAW_ARCHIVE_SHA256:
            msg = f"archive checksum mismatch: {digest}"
            raise ValueError(msg)

    rows = []
    with tarfile.open(paths.RAW_ARCHIVE, "r:gz") as tar:
        for member in tar:
            split = OFFICIAL_SPLITS.get(member.name)
            if split is None:
                continue
            f = tar.extractfile(member)
            if f is None:
                continue
            for line in f:
                rec = orjson.loads(line)
                text = rec["text"].get("en")
                if not text:
                    continue
                text = normalize_text(text)
                concepts = rec["eurovoc_concepts"]
                rows.append(
                    {
                        "celex_id": rec["celex_id"],
                        "publication_date": rec["publication_date"],
                        "official_split": split,
                        "text": text,
                        "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                        "n_chars": len(text),
                        **{f"labels_{lvl}": list(concepts[lvl]) for lvl in LEVELS},
                        "labels_all": list(concepts["all_levels"]),
                    }
                )

    df = pd.DataFrame(rows)
    df["publication_date"] = pd.to_datetime(df["publication_date"])
    if df["celex_id"].duplicated().any():
        dups = df.loc[df["celex_id"].duplicated(), "celex_id"].head().tolist()
        msg = f"duplicate celex ids in corpus: {dups}"
        raise ValueError(msg)
    df = df.sort_values(["official_split", "publication_date", "celex_id"]).reset_index(drop=True)
    df.to_parquet(paths.CORPUS, index=False)

    label_space = sorted({c for ls in df["labels_level_2"] for c in ls})
    paths.LABELS.write_bytes(orjson.dumps({"level_2": label_space}, option=orjson.OPT_INDENT_2))
    return df

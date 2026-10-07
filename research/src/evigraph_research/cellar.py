"""Fetch work-to-work relations for corpus documents from the EUR-Lex Cellar SPARQL endpoint.

For every corpus CELEX id we take all outgoing IRI-valued properties whose object is another
work with a CELEX id. Targets outside the corpus are kept: two corpus documents based on the
same external act are connected through it.

Label-bearing properties (EuroVoc, subject matter, directory code) point to concepts, not
works, so they never appear here. They must not be used as model inputs.
"""

import concurrent.futures as cf
import hashlib
import time

import httpx
import orjson
import pandas as pd

from evigraph_research import paths

ENDPOINT = "https://publications.europa.eu/webapi/rdf/sparql"
CDM = "http://publications.europa.eu/ontology/cdm#"
# Virtuoso truncates result sets silently; a batch that hits this size is split and retried.
ROW_CAP = 10_000

QUERY = """PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
SELECT DISTINCT ?src ?p ?dst WHERE {{
  VALUES ?src {{ {values} }}
  ?w cdm:resource_legal_id_celex ?src .
  ?w ?p ?o .
  FILTER(isIRI(?o) && ?o != ?w)
  ?o cdm:resource_legal_id_celex ?dst .
}}"""

# Relation families used by the graph report. Anything else is kept under its raw name.
RELATION_FAMILY = {
    "work_cites_work": "cites",
    "resource_legal_amends_resource_legal": "amends",
    "legislation_secondary_modifies_legislation_secondary": "amends",
    "resource_legal_repeals_resource_legal": "repeals",
    "resource_legal_implicitly_repeals_resource_legal": "repeals",
    "resource_legal_based_on_resource_legal": "based_on",
    "resource_legal_corrects_resource_legal": "corrects",
    "resource_legal_adopts_resource_legal": "adopts",
    "resource_legal_completes_resource_legal": "completes",
    "resource_legal_extends_resource_legal": "extends",
    "resource_legal_suspends_resource_legal": "suspends",
}


def _literal(celex: str) -> str:
    return '"' + celex.replace("\\", "\\\\").replace('"', '\\"') + '"^^xsd:string'


def _query(client: httpx.Client, celex_ids: list[str]) -> list[dict]:
    q = QUERY.format(values=" ".join(_literal(c) for c in celex_ids))
    for attempt in range(6):
        try:
            r = client.post(
                ENDPOINT,
                data={"query": q},
                headers={"Accept": "application/sparql-results+json"},
            )
            r.raise_for_status()
            bindings = r.json()["results"]["bindings"]
            break
        except (httpx.HTTPError, ValueError, KeyError):
            if attempt == 5:
                raise
            time.sleep(2**attempt)
    rows = [
        {"src": b["src"]["value"], "predicate": b["p"]["value"], "dst": b["dst"]["value"]}
        for b in bindings
    ]
    if len(rows) >= ROW_CAP and len(celex_ids) > 1:
        mid = len(celex_ids) // 2
        return _query(client, celex_ids[:mid]) + _query(client, celex_ids[mid:])
    return rows


def _batch_file(celex_ids: list[str]):
    key = hashlib.sha1("\n".join(celex_ids).encode()).hexdigest()[:16]
    return paths.CACHE / "cellar" / f"{key}.json"


def _fetch_batch(celex_ids: list[str]) -> int:
    out = _batch_file(celex_ids)
    if out.exists():
        return 0
    with httpx.Client(timeout=httpx.Timeout(180.0)) as client:
        rows = _query(client, celex_ids)
    tmp = out.with_suffix(".tmp")
    tmp.write_bytes(orjson.dumps({"celex_ids": celex_ids, "rows": rows}))
    tmp.rename(out)
    return len(rows)


def fetch_all(*, batch_size: int = 200, workers: int = 4) -> pd.DataFrame:
    paths.ensure_dirs()
    (paths.CACHE / "cellar").mkdir(exist_ok=True)
    corpus = pd.read_parquet(paths.CORPUS, columns=["celex_id"])
    ids = sorted(corpus["celex_id"])
    batches = [ids[i : i + batch_size] for i in range(0, len(ids), batch_size)]
    todo = [b for b in batches if not _batch_file(b).exists()]
    print(f"{len(batches)} batches, {len(todo)} to fetch")

    started = time.monotonic()
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_fetch_batch, b) for b in todo]
        for done, fut in enumerate(cf.as_completed(futures), 1):
            fut.result()
            if done % 20 == 0 or done == len(futures):
                print(f"  {done}/{len(futures)} batches, {time.monotonic() - started:.0f}s")

    rows, queried = [], set()
    for b in batches:
        payload = orjson.loads(_batch_file(b).read_bytes())
        queried.update(payload["celex_ids"])
        rows.extend(payload["rows"])
    edges = pd.DataFrame(rows, columns=["src", "predicate", "dst"]).drop_duplicates()
    edges["predicate"] = edges["predicate"].str.removeprefix(CDM)
    edges["family"] = edges["predicate"].map(RELATION_FAMILY).fillna("other:" + edges["predicate"])
    corpus_ids = set(ids)
    edges["dst_in_corpus"] = edges["dst"].isin(corpus_ids)
    edges.to_parquet(paths.CELLAR_EDGES, index=False)

    found = edges["src"].nunique()
    print(f"edges: {len(edges)}; corpus docs with >=1 outgoing edge: {found}/{len(queried)}")
    return edges

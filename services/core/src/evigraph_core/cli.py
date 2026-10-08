"""Command line: `uv run evigraph-core <command>`."""

import time
import uuid
from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the HTTP API."""
    import uvicorn

    from evigraph_core.app import create_app

    uvicorn.run(create_app(), host=host, port=port)


@app.command()
def migrate() -> None:
    """Apply database migrations (EVIGRAPH_DATABASE_URL)."""
    from alembic import command
    from alembic.config import Config

    root = Path(__file__).resolve().parents[2]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))
    command.upgrade(cfg, "head")


@app.command("demo-multieurlex")
def demo_multieurlex(
    corpus: Annotated[Path, typer.Option(help="research/data/interim/corpus_en.parquet")],
    reviewed: int = 2000,
    new: int = 200,
    alpha: float = 0.1,
    seed: int = 0,
) -> None:
    """End-to-end product run on MultiEURLEX: catalog, ingestion, simulated expert review of
    `reviewed` documents, training, certification, suggestions for `new` documents."""
    import pandas as pd

    from evigraph_core import catalogs, certification, documents, releases, reviews
    from evigraph_core.db import get_engine, session_factory
    from evigraph_core.models import Catalog, Project
    from evigraph_core.settings import get_settings

    settings = get_settings()
    factory = session_factory(get_engine(settings.database_url))
    df = pd.read_parquet(corpus, columns=["celex_id", "official_split", "text", "labels_level_2"])
    train = df[df["official_split"] == "train"].sample(reviewed, random_state=seed)
    fresh = df[df["official_split"] == "dev"].sample(new, random_state=seed)
    keys = sorted({k for ls in df["labels_level_2"] for k in ls})
    t0 = time.perf_counter()

    with factory() as s:
        project = Project(name=f"multieurlex-demo-{uuid.uuid4().hex[:6]}")
        s.add(project)
        s.flush()
        catalog = Catalog(project_id=project.id, name="EuroVoc level 2")
        s.add(catalog)
        s.flush()
        version = catalogs.create_version(
            s, catalog=catalog, concepts=[catalogs.ConceptSpec(k, f"EuroVoc {k}") for k in keys]
        )
        catalogs.publish(s, version)
        s.commit()
        concept_ids = {c.key: c.id for c in version.concepts}
        typer.echo(f"project {project.id}, catalog version {version.id}, {len(keys)} concepts")

    for i, row in enumerate(train.itertuples()):
        with factory() as s:
            dv = documents.create_document(
                s,
                project_id=project.id,
                title=row.celex_id,
                raw_text=row.text,
                source=documents.SourceRef("eur-lex", row.celex_id),
                settings=settings,
            )
            for k in row.labels_level_2:  # the "expert" adds every gold concept, then completes
                reviews.add_concept(
                    s,
                    document_version_id=dv.id,
                    concept_id=concept_ids[k],
                    reviewer="demo",
                    idempotency_key=uuid.uuid4().hex,
                )
            reviews.complete(
                s,
                document_version_id=dv.id,
                catalog_version_id=version.id,
                reviewer="demo",
                idempotency_key=uuid.uuid4().hex,
            )
            s.commit()
        if (i + 1) % 500 == 0:
            typer.echo(f"  reviewed {i + 1}/{len(train)} ({time.perf_counter() - t0:.0f}s)")

    with factory() as s:
        release = releases.train(s, version.id, settings)
        s.commit()
        typer.echo(f"release {release.id}: {release.manifest}")
    with factory() as s:
        cert = certification.certify_release(
            s, release_id=release.id, alpha=alpha, delta=0.1, settings=settings
        )
        s.commit()
        typer.echo(
            f"certification {cert.status}: tau={cert.tau} on {cert.cert_documents} documents, "
            f"{cert.n_errors}/{cert.n_applied} errors, ucb={cert.ucb}, "
            f"auto_recall={cert.auto_recall}, reason={cert.status_reason}"
        )

    hits = auto = errors = gold_total = 0
    for row in fresh.itertuples():
        with factory() as s:
            dv = documents.create_document(
                s,
                project_id=project.id,
                title=row.celex_id,
                raw_text=row.text,
                source=None,
                settings=settings,
            )
            _, _, items = releases.suggest(
                s,
                document_version_id=dv.id,
                catalog_version_id=version.id,
                top_k=5,
                settings=settings,
            )
            s.commit()
        gold = set(row.labels_level_2)
        gold_total += len(gold)
        hits += items[0].concept.key in gold
        for it in items:
            if it.decision == "auto_applied":
                auto += 1
                errors += it.concept.key not in gold
    typer.echo(
        f"new documents: top-1 precision {hits / len(fresh):.3f}; auto-applied {auto} tags, "
        f"realised error rate {errors / max(auto, 1):.3f}, "
        f"auto recall {(auto - errors) / max(gold_total, 1):.3f}; "
        f"total {time.perf_counter() - t0:.0f}s"
    )


def main() -> None:
    app()

"""Command line entry points: `uv run evigraph-research <command>`."""

import typer

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command()
def prepare(*, verify: bool = True) -> None:
    """Extract English MultiEURLEX with level 1-3 labels."""
    from evigraph_research import prepare as mod

    df = mod.extract(verify=verify)
    typer.echo(df.groupby("official_split").size().to_string())


@app.command()
def cellar(batch_size: int = 200, workers: int = 4) -> None:
    """Fetch document-to-document relations and metadata from the EUR-Lex Cellar SPARQL endpoint."""
    from evigraph_research import cellar as mod

    mod.fetch_all(batch_size=batch_size, workers=workers)


@app.command()
def dedup(threshold: float = 0.9) -> None:
    """Find exact and near-duplicate documents (MinHash LSH)."""
    from evigraph_research import dedup as mod

    mod.run(threshold=threshold)


@app.command()
def splits(model_dev_size: int = 5000, seed: int = 20261007) -> None:
    """Build the grouped five-way split manifest."""
    from evigraph_research import splits as mod

    mod.build(model_dev_size=model_dev_size, seed=seed)


@app.command("graph-report")
def graph_report() -> None:
    """Coverage and label homophily of the EUR-Lex graph (go/no-go for graph hypotheses)."""
    from evigraph_research import graph_report as mod

    mod.run()


@app.command()
def baseline(n_features: int = 2**21, alpha: float = 0.05, delta: float = 0.1) -> None:
    """TF-IDF + linear baseline, simple graph feature, calibration and risk-controlled policy."""
    from evigraph_research import baseline as mod

    mod.run(n_features=n_features, alpha=alpha, delta=delta)


@app.command("strong-text")
def strong_text(max_steps: int | None = None, epochs: int | None = None, seed: int = 0) -> None:
    """Fine-tune the strong text control (LEGAL-BERT). --max-steps N only benchmarks speed."""
    from evigraph_research import strong as mod

    typer.echo(mod.run(max_steps=max_steps, epochs=epochs, seed=seed))


@app.command()
def compare() -> None:
    """Protocol v1: pre-registered systems, certification and H1 contrasts."""
    from evigraph_research import compare as mod

    mod.run()


@app.command()
def h2(version: str = "2.1") -> None:
    """Protocol 2.x: certified tagging under source duplication (--version 2.0 or 2.1)."""
    from evigraph_research import h2 as mod
    from evigraph_research import protocol_v2, protocol_v21

    mod.run({"2.0": protocol_v2, "2.1": protocol_v21}[version])


@app.command("predict-final")
def predict_final(seed: int = 0) -> None:
    """Protocol 3.0: LEGAL-BERT predictions on final_test (opens the sealed split, logged)."""
    from evigraph_research import strong as mod

    typer.echo(mod.predict_final(seed))


@app.command()
def final(*, dry_run: bool = False) -> None:
    """Protocol 3.0: the single final_test evaluation (--dry-run uses risk_cert instead)."""
    from evigraph_research import final as mod

    mod.run(dry_run=dry_run, seeds=(0,) if dry_run else mod.cfg.SEEDS)


def main() -> None:
    app()

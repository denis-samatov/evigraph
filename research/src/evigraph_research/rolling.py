"""Protocol 4.1 runner: rolling re-certification under temporal drift (H5).

Systems, scores and grids come from `v4.prepare` (protocol 4.0). Built-in check: H4 recomputed
from the same preparation must equal the stored protocol 4.0 results.
"""

import time
from typing import Any

import numpy as np
import orjson
import pandas as pd

from evigraph_research import paths, policy, protocol, v4
from evigraph_research import protocol_v4 as v4cfg
from evigraph_research import protocol_v41 as cfg
from evigraph_research.baseline import Timer
from evigraph_research.final import _auto_recall, _risk
from evigraph_research.h2 import _doc_stats


def _windows(dates: pd.Series) -> tuple[list[pd.Period], dict[pd.Period, np.ndarray]]:
    """Evaluation quarters and the positions (within final_test) of each quarter's acts."""
    quarter = dates.dt.to_period("Q")
    first = pd.Period(cfg.FIRST_EVALUATION_QUARTER, freq="Q")
    members = {q: np.flatnonzero((quarter == q).to_numpy()) for q in quarter.unique()}
    evaluation = sorted(
        q for q, m in members.items() if q >= first and len(m) >= cfg.MIN_QUARTER_DOCS
    )
    return evaluation, members


def _history(quarter: pd.Period, members: dict, months: int | None) -> np.ndarray:
    """Acts published before `quarter`: the preceding `months`, or everything if None."""
    past = [q for q in members if q < quarter and (months is None or q >= quarter - months // 3)]
    return np.sort(np.concatenate([members[q] for q in past])) if past else np.array([], int)


def run() -> dict:
    timer = Timer()
    p = v4.prepare("protocol 4.1 (rolling re-certification)", timer)
    y_ft = p.y[p.ft]
    dates = p.fr["publication_date"].iloc[p.ft].reset_index(drop=True)
    evaluation, members = _windows(dates)

    with timer.stage("check_h4"):
        stored = orjson.loads((paths.REPORTS / v4cfg.RESULTS_FILE).read_bytes())["h4"]
        again = orjson.loads(orjson.dumps(v4._h4(p.fitted, p.fr, p.y, p.ft)))
        if again != stored:
            msg = "v4.prepare no longer reproduces the protocol 4.0 H4 results"
            raise protocol.ProtocolError(msg)

    one_off_pool = _history(evaluation[0], members, None)
    results: dict[str, Any] = {
        "protocol": cfg.PROTOCOL_VERSION,
        "evaluation_quarters": {str(q): len(members[q]) for q in evaluation},
        "one_off_pool": len(one_off_pool),
        "checks": {"h4_reproduced": True},
        "seeds": {},
    }
    with timer.stage("rolling"):
        for seed, systems in p.fitted.items():
            out: dict[str, Any] = {}
            for name in cfg.SYSTEMS:
                f = systems[name]
                s = f["s_ft"]

                def certify(rows: np.ndarray, alpha: float, f=f, s=s) -> float | None:
                    if not len(rows):
                        return None
                    return policy.certify(
                        s[rows], y_ft[rows], f["grid"], alpha=alpha, delta=protocol.DELTA
                    ).tau

                out[name] = {}
                for a in (cfg.ALPHA, cfg.ALPHA_SECONDARY):
                    one_off_tau = certify(one_off_pool, a)
                    by_scheme: dict[str, Any] = {}
                    for scheme in cfg.SCHEMES:
                        draws = cfg.SAMPLE_DRAWS if scheme == "rolling_6m_sample" else 1
                        pooled, per_quarter = [], {str(q): [] for q in evaluation}
                        uncertified = 0
                        for d in range(draws):
                            stats = []
                            for q in evaluation:
                                rows = members[q]
                                if scheme == "original":
                                    tau = f["tau"][a]
                                elif scheme == "one_off":
                                    tau = one_off_tau
                                elif scheme == "rolling_6m":
                                    tau = certify(_history(q, members, 6), a)
                                elif scheme == "rolling_12m":
                                    tau = certify(_history(q, members, 12), a)
                                else:
                                    window = _history(q, members, 6)
                                    rng = np.random.default_rng([d, q.year, q.quarter])
                                    sample = rng.choice(
                                        window, min(cfg.SAMPLE_SIZE, len(window)), replace=False
                                    )
                                    tau = certify(sample, a)
                                uncertified += tau is None
                                auto = (
                                    s[rows] >= tau if tau is not None else np.zeros_like(y_ft[rows])
                                )
                                st = _doc_stats(y_ft[rows], auto)
                                stats.append(st)
                                per_quarter[str(q)].append(_risk(st))
                            pooled.append(np.vstack(stats))
                        risks = [_risk(st) for st in pooled]
                        quarters = {
                            q: round(float(np.nanmean(v)), 4) if np.isfinite(v).any() else None
                            for q, v in per_quarter.items()
                        }
                        by_scheme[scheme] = {
                            "pooled_risk": round(float(np.nanmean(risks)), 4),
                            "pooled_risk_max_over_draws": round(float(np.nanmax(risks)), 4),
                            "pooled_auto_recall": round(
                                float(np.mean([_auto_recall(st) for st in pooled])), 4
                            ),
                            "quarters_above_alpha": round(
                                float(
                                    np.mean(
                                        [
                                            sum(r > a for r in qr if np.isfinite(r))
                                            for qr in zip(*per_quarter.values(), strict=True)
                                        ]
                                    )
                                ),
                                2,
                            ),
                            "uncertified_quarters": round(uncertified / draws, 2),
                            "risk_by_quarter": quarters,
                        }
                    out[name][str(a)] = by_scheme
            results["seeds"][str(seed)] = out

    a = str(cfg.ALPHA_SECONDARY)
    met = {
        s: r["C1_strong+knn"][a]["rolling_6m"]["pooled_risk"] <= cfg.ALPHA_SECONDARY
        for s, r in results["seeds"].items()
    }
    results["summary"] = {
        "H5_rolling_6m_C1_alpha_005": f"{sum(met.values())} of {len(met)}",
        "pooled_risk": {
            s: {scheme: r["C1_strong+knn"][a][scheme]["pooled_risk"] for scheme in cfg.SCHEMES}
            for s, r in results["seeds"].items()
        },
    }
    results["cost"] = {"stages_s": timer.stages}
    (paths.REPORTS / cfg.RESULTS_FILE).write_bytes(
        orjson.dumps(results, option=orjson.OPT_INDENT_2 | orjson.OPT_NON_STR_KEYS)
    )
    print(orjson.dumps(results["summary"], option=orjson.OPT_INDENT_2).decode())
    return results


if __name__ == "__main__":
    t0 = time.perf_counter()
    run()
    print(f"{time.perf_counter() - t0:.0f}s")

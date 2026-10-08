"""Render the protocol v1 comparison (reports/comparison_v1.json) as markdown tables."""

import orjson

from evigraph_research import paths, protocol


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{100 * x:.1f}%"


def _num(x: float | None, digits: int = 3) -> str:
    return "—" if x is None else f"{x:.{digits}f}"


def render() -> str:
    r = orjson.loads((paths.REPORTS / "comparison_v1.json").read_bytes())
    systems = r["systems"]
    a = str(protocol.ALPHA_PRIMARY)
    lines = [
        f"Protocol {r['protocol']}; strong model epoch: {r['strong_text_epoch']}; "
        f"evaluation documents with C2 neighbours: {_pct(r['nbtext_coverage_eval'])}.",
        "",
        "**Ranking quality**",
        "",
        "| System | mRP model_dev (OOF) | macro-F1 model_dev "
        "| mRP risk_cert | top-10 ECE risk_cert |",
        "|---|---|---|---|---|",
    ]
    for name, s in systems.items():
        dev, cert = s["model_dev_oof"], s["risk_cert"]
        lines.append(
            f"| {name} | {_num(dev['mrp'])} | {_num(dev['macro_f1'])} "
            f"| {_num(cert['mrp'])} | {_num(cert['ece_top10_pairs'])} |"
        )
    lines += [
        "",
        f"**Certified automation on risk_cert (δ = {protocol.DELTA})**",
        "",
        "| System | AutoRecall α=0.05 | AutoRecall α=0.10 | 95% CI (α=0.10) "
        "| Realised risk α=0.10 | Auto tags per document α=0.10 |",
        "|---|---|---|---|---|---|",
    ]
    for name, s in systems.items():
        p05, p10 = s["policy"]["0.05"], s["policy"][a]
        lo, hi = s["auto_recall_primary_ci95"]
        lines.append(
            f"| {name} | {_pct(p05['auto_recall'])} | {_pct(p10['auto_recall'])} "
            f"| {_pct(lo)}–{_pct(hi)} | {_pct(p10['risk'])} | {_num(p10['auto_per_doc'], 2)} |"
        )
    h1 = r["h1"]
    lines += [
        "",
        f"**H1: AutoRecall contrasts at α = {h1['alpha']}, paired document bootstrap**",
        "",
        "| Treatment − control | AutoRecall difference | 95% CI | 95% CI of mRP difference |",
        "|---|---|---|---|",
    ]
    for c in h1["contrasts"]:
        lo, hi = c["auto_recall_diff_ci95"]
        mlo, mhi = c["model_dev_mrp_diff_ci95"]
        lines.append(
            f"| {c['treatment']} − {c['control']} | {100 * c['auto_recall_diff']:+.1f} pp "
            f"| {100 * lo:+.1f} … {100 * hi:+.1f} pp | {mlo:+.3f} … {mhi:+.3f} |"
        )
    verdict = "yes" if h1["graph_adds_beyond_text"] else "no"
    lines += [
        "",
        f"**Decision by the protocol rule — the graph adds information beyond text: {verdict}.**",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    print(render())

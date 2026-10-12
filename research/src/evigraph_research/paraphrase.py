"""Protocol 4.2 runner: LLM-paraphrased copies (H6).

Paraphrases are generated once through the DeepSeek API (OpenAI-compatible chat completions)
and cached in data/cache/paraphrase/<model>.jsonl, so evaluation reruns make no API calls.
The API key is read from DEEPSEEK_API_KEY or from a `.env` file in research/ or the repository
root (both are git-ignored). Built-in check: the exact-copy scenario must reproduce protocol
4.0 on the same targets.
"""

import asyncio
import hashlib
import os
import time
from typing import Any

import httpx
import numpy as np
import orjson

from evigraph_research import paths, protocol, provenance, v4
from evigraph_research import protocol_v3 as v3
from evigraph_research import protocol_v4 as v4cfg
from evigraph_research import protocol_v42 as cfg
from evigraph_research.baseline import Timer

CACHE = paths.CACHE / "paraphrase" / f"{cfg.MODEL}.jsonl"
LEVELS = tuple(cfg.PROMPTS)


def _api_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY")
    if key:
        return key
    for env in (paths.ROOT / ".env", paths.ROOT.parent / ".env"):
        if env.exists():
            for line in env.read_text().splitlines():
                name, _, value = line.partition("=")
                if name.strip() == "DEEPSEEK_API_KEY" and value.strip():
                    return value.strip().strip("'\"")
    msg = "DEEPSEEK_API_KEY is not set (environment or research/.env)"
    raise RuntimeError(msg)


def truncate(text: str) -> str:
    if len(text) <= cfg.MAX_SOURCE_CHARS:
        return text
    cut = text.rfind(" ", 0, cfg.MAX_SOURCE_CHARS)
    return text[: cut if cut > 0 else cfg.MAX_SOURCE_CHARS]


def _prompt_sha(level: str) -> str:
    return hashlib.sha256((cfg.SYSTEM + cfg.PROMPTS[level]).encode()).hexdigest()[:12]


def _load_cache() -> dict[tuple[str, str, int], dict]:
    out = {}
    if CACHE.exists():
        for line in CACHE.read_bytes().splitlines():
            r = orjson.loads(line)
            out[r["celex_id"], r["level"], r["k"]] = r
    return out


async def _one(client, sem, key, job: tuple[str, str, int, str]) -> dict:
    celex, level, k, source = job
    body = {
        "model": cfg.MODEL,
        "temperature": cfg.TEMPERATURE,
        "max_tokens": cfg.MAX_OUTPUT_TOKENS,
        "thinking": cfg.THINKING,
        "messages": [
            {"role": "system", "content": cfg.SYSTEM},
            {"role": "user", "content": cfg.PROMPTS[level] + source},
        ],
    }
    last = ""
    async with sem:
        for attempt in range(cfg.RETRIES):
            try:
                r = await client.post(
                    "/chat/completions", json=body, headers={"Authorization": f"Bearer {key}"}
                )
                if r.status_code == 200:
                    data = r.json()
                    text = (data["choices"][0]["message"]["content"] or "").strip()
                    if text:
                        return {
                            "celex_id": celex,
                            "level": level,
                            "k": k,
                            "text": text,
                            "model": data.get("model"),
                            "finish_reason": data["choices"][0].get("finish_reason"),
                            "usage": data.get("usage", {}),
                            "prompt_sha": _prompt_sha(level),
                        }
                    last = "empty completion"
                else:
                    last = f"HTTP {r.status_code}: {r.text[:200]}"
            except httpx.HTTPError as e:
                last = f"{type(e).__name__}: {e}"
            await asyncio.sleep(2**attempt * 2)
    return {"celex_id": celex, "level": level, "k": k, "error": last}


async def _generate(jobs: list[tuple[str, str, int, str]], concurrency: int = 16) -> list[dict]:
    key = _api_key()
    sem = asyncio.Semaphore(concurrency)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    done: list[dict] = []
    timeout = httpx.Timeout(300.0, connect=30.0)
    async with httpx.AsyncClient(base_url=cfg.API_BASE, timeout=timeout) as client:
        tasks = [asyncio.create_task(_one(client, sem, key, job)) for job in jobs]
        with CACHE.open("ab") as f:
            for n, task in enumerate(asyncio.as_completed(tasks), 1):
                r = await task
                if "error" not in r:
                    f.write(orjson.dumps(r) + b"\n")
                    f.flush()
                done.append(r)
                if n % 100 == 0 or n == len(jobs):
                    failed = sum("error" in x for x in done)
                    print(f"  generated {n}/{len(jobs)}, failed {failed}", flush=True)
    return done


def _sources(p: v4.Prepared) -> tuple[np.ndarray, np.ndarray]:
    """Protocol 4.0 final_test targets and their sources (train positions), as in v4.run."""
    earlier3 = np.sort(
        np.random.default_rng(v3.FINAL_TARGET_SEED).choice(p.ft, v3.TARGETS, replace=False)
    )
    targets = np.sort(
        np.random.default_rng(v4cfg.FINAL_TARGET_SEED).choice(
            np.setdiff1d(p.ft, earlier3), v4cfg.TARGETS, replace=False
        )
    )
    _, _, _, top1 = provenance.knn_both(
        p.query(targets), p.x_train, p.y_train, k=protocol.KNN_K, groups=None
    )
    return targets, np.unique(top1)


def run(*, estimate: bool = False, group_identical: bool = False) -> dict:
    timer = Timer()
    p = v4.prepare("protocol 4.2 (paraphrased copies of final_test targets' sources)", timer)
    targets, sources = _sources(p)
    celex = p.fr["celex_id"].to_numpy()
    src_celex = [str(celex[p.train_idx[s]]) for s in sources]
    src_text = {
        c: truncate(p.texts[p.train_idx[s]]) for c, s in zip(src_celex, sources, strict=True)
    }
    cache = _load_cache()
    jobs = [
        (c, level, k, src_text[c])
        for c in src_celex
        for level in LEVELS
        for k in range(cfg.VARIANTS)
        if (c, level, k) not in cache
    ]
    chars = sum(len(j[3]) for j in jobs)
    plan = {
        "sources": len(sources),
        "calls_needed": len(jobs),
        "calls_cached": len(sources) * len(LEVELS) * cfg.VARIANTS - len(jobs),
        "input_chars": chars,
        # about 4 characters per token for English legal text; output about as long as input
        "estimated_tokens_in_out": round(chars / 4 + len(jobs) * 60),
    }
    print(orjson.dumps(plan, option=orjson.OPT_INDENT_2).decode(), flush=True)
    if estimate:
        return plan

    generation: dict[str, Any] = {}
    if jobs:
        with timer.stage("generate"):
            out = asyncio.run(_generate(jobs))
        failed = [r for r in out if "error" in r]
        generation = {"calls": len(out), "failed": len(failed)}
        if failed:
            generation["errors"] = sorted({r["error"][:120] for r in failed})[:5]
        cache = _load_cache()
    usage = [r.get("usage", {}) for r in cache.values() if r["celex_id"] in src_text]
    generation["prompt_tokens"] = sum(u.get("prompt_tokens", 0) for u in usage)
    generation["completion_tokens"] = sum(u.get("completion_tokens", 0) for u in usage)
    generation["models_reported"] = sorted({str(r.get("model")) for r in cache.values()})
    generation["finish_reasons"] = dict(
        sorted(
            {
                fr: sum(r.get("finish_reason") == fr for r in cache.values())
                for fr in {r.get("finish_reason") for r in cache.values()}
            }.items(),
            key=lambda kv: str(kv[0]),
        )
    )

    per_variant = cfg.COPIES // cfg.VARIANTS
    reused = {level: 0 for level in LEVELS}

    def variants(c: str, level: str) -> list[str]:
        got = [cache[c, level, k]["text"] for k in range(cfg.VARIANTS) if (c, level, k) in cache]
        if not got:
            msg = f"no {level} paraphrase for {c}; rerun to retry generation"
            raise RuntimeError(msg)
        reused[level] += cfg.VARIANTS - len(got)
        return [got[k % len(got)] for k in range(cfg.VARIANTS)]

    def make_texts(kind: str, srcs: np.ndarray) -> list[str]:
        out: list[str] = []
        for s in srcs:
            c = str(celex[p.train_idx[s]])
            if kind == "truncated":
                out.extend([src_text[c]] * cfg.COPIES)
            else:
                v = variants(c, kind)
                out.extend(v[i // per_variant] for i in range(cfg.COPIES))
        return out

    with timer.stage("evaluate"):
        h6 = v4._h3(
            targets=targets,
            x_q=p.query(targets),
            x_train=p.x_train,
            y_train=p.y_train,
            groups_train=p.groups_train,
            texts=p.texts,
            train_idx=p.train_idx,
            tf=p.tf,
            vocab=[],
            words_of=_words_of(p),
            fitted=p.fitted,
            base=p.base,
            y=p.y,
            prior=p.prior,
            n_lab=p.n_lab,
            n_jobs=p.n_jobs,
            timer=timer,
            scenarios=[(s, 0.0) for s in cfg.SCENARIOS],
            make_texts=make_texts,
            group_identical=group_identical,
        )
    h6.pop("H3_met", None)
    for r in h6["seeds"].values():
        r.pop("H3_met", None)
    generation["variants_reused_for_failed_generations"] = reused

    stored = orjson.loads((paths.REPORTS / v4cfg.RESULTS_FILE).read_bytes())["h3"]["final_test"]
    exact_now = _row(h6["seeds"]["0"]["table"], "exact", "C1_strong+knn", "naive")
    exact_4 = _row(stored["seeds"]["0"]["table"], "exact", "C1_strong+knn", "naive")
    if exact_now["risk_targets"] != exact_4["risk_targets"]:
        msg = "exact-copy scenario does not reproduce protocol 4.0"
        raise protocol.ProtocolError(msg)

    full = next(a for a in h6["attribution"] if a["kind"] == "paraphrase_full")
    attribution_ok = all(full[m]["attributed"] < 0.5 for m in v4cfg.ATTRIBUTION)
    decision = {}
    for seed, r in h6["seeds"].items():
        harm = _row(r["table"], "paraphrase_full", "C1_strong+knn", "naive")
        decision[seed] = bool(attribution_ok and harm["risk_change_ci95"][0] > 0)
    results = {
        "protocol": cfg.PROTOCOL_VERSION,
        "model": cfg.MODEL,
        "plan": plan,
        "generation": generation,
        "checks": {"exact_reproduces_protocol_40": exact_now["risk_targets"]},
        "h6": h6,
        "summary": {
            "H6_paraphrase_full_evades_and_harms": f"{sum(decision.values())} of {len(decision)}",
            "attribution_paraphrase_full": {m: full[m]["attributed"] for m in v4cfg.ATTRIBUTION},
            "naive_harm_paraphrase_full": {
                s: _row(r["table"], "paraphrase_full", "C1_strong+knn", "naive")["risk_change"]
                for s, r in h6["seeds"].items()
            },
        },
        "cost": {"stages_s": timer.stages},
    }
    if group_identical:  # exploratory, not part of the registered protocol
        results["exploratory"] = "unattributed identical copies grouped together (post hoc)"
    name = "protocol_v42_grouped_identical.json" if group_identical else cfg.RESULTS_FILE
    (paths.REPORTS / name).write_bytes(
        orjson.dumps(results, option=orjson.OPT_INDENT_2 | orjson.OPT_NON_STR_KEYS)
    )
    print(orjson.dumps(results["summary"], option=orjson.OPT_INDENT_2).decode())
    return results


def _row(table: list[dict], kind: str, system: str, attribution: str) -> dict:
    return next(
        r
        for r in table
        if (r["kind"], r["system"], r["attribution"]) == (kind, system, attribution)
    )


def _words_of(p: v4.Prepared):
    cache: dict[int, set[str]] = {}

    def words_of(i: int) -> set[str]:
        if i not in cache:
            cache[i] = v4._words(p.texts[p.train_idx[i]])
        return cache[i]

    return words_of


if __name__ == "__main__":
    t0 = time.perf_counter()
    run(estimate=True)
    print(f"{time.perf_counter() - t0:.0f}s")

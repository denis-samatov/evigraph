"""Strong text control: fine-tuned LEGAL-BERT, multi-label head over the 127 level-2 concepts.

Protocol (docs/PROTOCOL.md, section "Strong text model"):
* input: first STRONG_MAX_TOKENS word pieces of the canonical text;
* fit on train minus an early-stopping subset = the latest EARLY_STOP_SHARE of train groups;
  the epoch with the best mRP on that subset is kept; model_dev is not used for selection;
* predictions are written for model_dev, calib_fit and risk_cert. final_test is not tokenised.

Known caveat: LEGAL-BERT was pre-trained (MLM, no labels) on EU legislation from EUR-Lex,
which includes the texts of all splits.
"""

import gc
import math
import time
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import orjson
import torch
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    get_linear_schedule_with_warmup,
)

from evigraph_research import dataset, metrics, paths, protocol

PRE_TRUNCATE_CHARS = 8_000  # enough for 512 word pieces; saves tokenizer time
OUT_DIR = paths.CACHE / "strong"
PREDS = paths.STRONG_PREDS


def _device() -> torch.device:
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def early_stop_mask(frame, is_train: np.ndarray, share: float) -> np.ndarray:
    """Latest `share` of train documents, extended to whole split groups."""
    tr = frame[is_train]
    cutoff = tr["publication_date"].quantile(1 - share)
    first = tr.groupby("split_group")["publication_date"].transform("min")
    es_groups = set(tr.loc[first >= cutoff, "split_group"])
    return is_train & frame["split_group"].isin(es_groups).to_numpy()


def tokenize(texts: list[str], tokenizer, max_tokens: int) -> list[np.ndarray]:
    enc = tokenizer(
        [t[:PRE_TRUNCATE_CHARS] for t in texts],
        truncation=True,
        max_length=max_tokens,
        add_special_tokens=True,
    )
    return [np.asarray(ids, dtype=np.int32) for ids in enc["input_ids"]]


def _batch(
    ids: list[np.ndarray], device: torch.device, width: int | None = None
) -> dict[str, torch.Tensor]:
    """Pad to `width`, or to the batch maximum rounded up to 64.

    MPS recompiles its graph for every new input shape, so the number of distinct shapes is
    kept small: training always uses the full width, prediction a few buckets.
    """
    if width is None:
        width = -(-max(len(x) for x in ids) // 64) * 64
    inp = np.zeros((len(ids), width), dtype=np.int64)
    att = np.zeros((len(ids), width), dtype=np.int64)
    for i, x in enumerate(ids):
        inp[i, : len(x)] = x
        att[i, : len(x)] = 1
    return {
        "input_ids": torch.from_numpy(inp).to(device),
        "attention_mask": torch.from_numpy(att).to(device),
    }


@torch.no_grad()
def predict(model, ids: list[np.ndarray], device: torch.device, batch: int = 32) -> np.ndarray:
    model.eval()
    order = np.argsort([len(x) for x in ids])
    out = np.zeros((len(ids), model.config.num_labels), dtype=np.float32)
    for lo in range(0, len(ids), batch):
        sel = order[lo : lo + batch]
        logits = model(**_batch([ids[i] for i in sel], device)).logits
        out[sel] = torch.sigmoid(logits.float()).cpu().numpy()
    return out


def _paths(seed: int) -> dict[str, Path]:
    """Seed 0 keeps the file names of protocol 1.0; other seeds get their own."""
    rev = protocol.STRONG_TEXT_REVISION[:8]
    tag = "" if seed == 0 else f"_seed{seed}"
    return {
        "preds": PREDS if seed == 0 else PREDS.with_name(f"p_strong_seed{seed}.joblib"),
        "checkpoint": OUT_DIR / f"checkpoint_{rev}{tag}.pt",
        "best": OUT_DIR / f"best_{rev}_seed{seed}.pt",
        "summary": paths.REPORTS / f"strong_text{tag}.json",
        "log": paths.REPORTS / f".strong{tag}.log",
        "final": PREDS.with_name(f"p_strong_final_seed{seed}.joblib"),
    }


def run(
    *, max_steps: int | None = None, epochs: int | None = None, seed: int = protocol.STRONG_SEED
) -> dict:
    """Fine-tune and write predictions. `max_steps` limits a smoke/benchmark run (no outputs)."""
    files = _paths(seed)
    torch.manual_seed(seed)
    epochs = epochs or protocol.STRONG_EPOCHS
    device = _device()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PREDS.parent.mkdir(parents=True, exist_ok=True)
    log = files["log"].open("a", buffering=1)

    def say(msg: str) -> None:
        line = f"{time.strftime('%H:%M:%S')} {msg}"
        print(line, flush=True)
        log.write(line + "\n")

    tok_name, rev = protocol.STRONG_TEXT_MODEL, protocol.STRONG_TEXT_REVISION
    tok_path = OUT_DIR / f"tokens_{rev[:8]}_{protocol.STRONG_MAX_TOKENS}.joblib"
    # Texts are only needed to build the token cache; keeping 0.5 GB of strings next to a
    # 110M-parameter model on a 16 GB machine pushes training into swap.
    ds = dataset.load(with_text=not tok_path.exists())
    protocol.assert_manifest(ds.frame)
    fr, y = ds.frame, ds.y
    is_train = ds.mask("train")
    es = early_stop_mask(fr, is_train, protocol.EARLY_STOP_SHARE)
    fit_rows = np.flatnonzero(is_train & ~es)
    es_rows = np.flatnonzero(es)
    eval_rows = np.flatnonzero(ds.mask("model_dev", "calib_fit", "risk_cert"))

    if tok_path.exists():
        tokens = joblib.load(tok_path)
    else:
        tokenizer = AutoTokenizer.from_pretrained(tok_name, revision=rev)
        t0 = time.perf_counter()
        rows = np.concatenate([fit_rows, es_rows, eval_rows])
        ids = tokenize(fr["text"].iloc[rows].tolist(), tokenizer, protocol.STRONG_MAX_TOKENS)
        tokens = dict(zip(rows.tolist(), ids, strict=True))
        joblib.dump(tokens, tok_path)
        say(f"tokenised {len(rows)} docs in {time.perf_counter() - t0:.0f}s")
        fr = fr.drop(columns="text")
    del ds
    gc.collect()

    model = AutoModelForSequenceClassification.from_pretrained(
        tok_name,
        revision=rev,
        num_labels=y.shape[1],
        problem_type="multi_label_classification",
    ).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=protocol.STRONG_LR, weight_decay=0.01)
    steps_per_epoch = math.ceil(len(fit_rows) / protocol.STRONG_BATCH)
    total = steps_per_epoch * epochs
    sched = get_linear_schedule_with_warmup(opt, int(protocol.STRONG_WARMUP * total), total)
    loss_fn = torch.nn.BCEWithLogitsLoss()

    ckpt = files["checkpoint"]
    state: dict[str, Any] = {"epoch": 0, "history": [], "best_mrp": -1.0, "best_epoch": None}
    if ckpt.exists() and max_steps is None:
        saved = torch.load(ckpt, map_location="cpu", weights_only=False)
        model.load_state_dict(saved["model"])
        opt.load_state_dict(saved["opt"])
        sched.load_state_dict(saved["sched"])
        state = saved["state"]
        say(f"resumed after epoch {state['epoch']}")

    say(
        f"seed={seed} device={device} fit={len(fit_rows)} es={len(es_rows)} eval={len(eval_rows)} "
        f"steps/epoch={steps_per_epoch} epochs={epochs}"
    )
    y_t = torch.from_numpy(y.astype(np.float32))
    started = time.perf_counter()
    done_steps = state["epoch"] * steps_per_epoch
    for epoch in range(state["epoch"], epochs):
        model.train()
        perm = np.random.default_rng(seed + epoch).permutation(fit_rows)
        ep_start = time.perf_counter()
        for step in range(steps_per_epoch):
            sel = perm[step * protocol.STRONG_BATCH : (step + 1) * protocol.STRONG_BATCH]
            # gradient accumulation over micro-batches; same effective batch and mean loss
            for lo in range(0, len(sel), protocol.STRONG_MICRO_BATCH):
                micro = sel[lo : lo + protocol.STRONG_MICRO_BATCH]
                batch = _batch([tokens[i] for i in micro], device, protocol.STRONG_MAX_TOKENS)
                logits = model(**batch).logits
                loss = loss_fn(logits, y_t[micro].to(device)) * (len(micro) / len(sel))
                loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            opt.zero_grad(set_to_none=True)
            done_steps += 1
            if step % 50 == 0 or step == steps_per_epoch - 1:
                rate = (step + 1) / (time.perf_counter() - ep_start)
                eta = (total - done_steps) / rate
                say(
                    f"epoch {epoch + 1}/{epochs} step {step + 1}/{steps_per_epoch} "
                    f"loss {loss.item():.4f} {rate:.2f} it/s eta {eta / 60:.0f} min"
                )
            if max_steps is not None and done_steps >= max_steps:
                elapsed = time.perf_counter() - started
                say(f"benchmark: {max_steps} steps in {elapsed:.0f}s")
                return {"seconds_per_step": elapsed / max_steps, "steps_per_epoch": steps_per_epoch}

        p_es = predict(model, [tokens[i] for i in es_rows], device)
        mrp = metrics.r_precision(y[es_rows], p_es)
        state["history"].append({"epoch": epoch + 1, "es_mrp": round(mrp, 4)})
        say(f"epoch {epoch + 1} early-stop mRP {mrp:.4f}")
        if mrp > state["best_mrp"]:
            state["best_mrp"], state["best_epoch"] = mrp, epoch + 1
            p_eval = predict(model, [tokens[i] for i in eval_rows], device)
            joblib.dump(
                {
                    "celex_id": fr["celex_id"].iloc[eval_rows].tolist(),
                    "p": p_eval,
                    "epoch": epoch + 1,
                },
                files["preds"],
            )
            torch.save(model.state_dict(), files["best"])
            say(f"saved predictions and weights of epoch {epoch + 1}")
        state["epoch"] = epoch + 1
        torch.save(
            {
                "model": model.state_dict(),
                "opt": opt.state_dict(),
                "sched": sched.state_dict(),
                "state": state,
            },
            ckpt,
        )

    summary = {
        "seed": seed,
        "model": tok_name,
        "revision": rev,
        "best_epoch": state["best_epoch"],
        "history": state["history"],
        "train_minutes": round((time.perf_counter() - started) / 60, 1),
        "device": str(device),
    }
    files["summary"].write_bytes(orjson.dumps(summary, option=orjson.OPT_INDENT_2))
    say(f"done: {summary}")
    return summary


def predict_final(seed: int) -> Path:
    """Predictions of a trained seed on final_test. Opens the sealed split (logged)."""
    protocol.open_final_test(f"strong text predictions, seed {seed}")
    files = _paths(seed)
    device = _device()
    tok_name, rev = protocol.STRONG_TEXT_MODEL, protocol.STRONG_TEXT_REVISION
    ds = dataset.load(with_text=True)
    protocol.assert_manifest(ds.frame)
    rows = np.flatnonzero(ds.mask("final_test"))
    tokenizer = AutoTokenizer.from_pretrained(tok_name, revision=rev)
    ids = tokenize(ds.frame["text"].iloc[rows].tolist(), tokenizer, protocol.STRONG_MAX_TOKENS)
    model = AutoModelForSequenceClassification.from_pretrained(
        tok_name, revision=rev, num_labels=ds.y.shape[1], problem_type="multi_label_classification"
    )
    if files["best"].exists():
        model.load_state_dict(torch.load(files["best"], map_location="cpu"))
    else:  # seed 0 of protocol 1.0: the last checkpoint holds the best (final) epoch
        model.load_state_dict(
            torch.load(files["checkpoint"], map_location="cpu", weights_only=False)["model"]
        )
    model.to(device)
    p = predict(model, ids, device)
    joblib.dump({"celex_id": ds.frame["celex_id"].iloc[rows].tolist(), "p": p}, files["final"])
    return files["final"]

"""Query models through OpenRouter (SPEC §6).

Every call is cached in ``results/cache.sqlite`` under the key model|question|condition|repeat,
so a run can stop at any point and resume without paying twice. Each record keeps the full
request, the full raw response, token counts (incl. reasoning tokens), cost, latency and finish
reason. ``export_raw`` writes the cache to ``results/raw/<model>.jsonl`` for publication.

Spending: before each request the runner reserves that request's worst-case cost (prompt +
``max_tokens`` of output at the model's price). It never starts a request that could take total
spend past ``max_cost``, so the cap holds even with many requests in flight.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import random
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import httpx
import yaml

from .questions import load_questions, render_prompt
from .sources import ROOT

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODELS_URL = "https://openrouter.ai/api/v1/models"
RESULTS_DIR = ROOT / "results"
CACHE_PATH = RESULTS_DIR / "cache.sqlite"
RAW_DIR = RESULTS_DIR / "raw"
PRICING_PATH = RESULTS_DIR / "pricing.json"
MODELS_CONFIG = ROOT / "config" / "models.yaml"
REPEATS = (1, 2, 3)  # extra runs of the repeat sample (repeat 0 is the main run)
TRANSIENT_STATUS = {408, 409, 425, 429, 500, 502, 503, 504, 520, 522, 524, 529}


# --------------------------------------------------------------------------------------
# Configuration and pricing


def load_config(path: Path = MODELS_CONFIG) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_api_key(name: str = "OPENROUTER_API_KEY", required: bool = True) -> str | None:
    """An API key from the environment, else from the project's .env file."""
    key = os.environ.get(name, "").strip()
    env = ROOT / ".env"
    if not key and env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            var, _, value = line.partition("=")
            if var.strip() == name:
                key = value.strip().strip("'\"")
    if not key and required:
        raise RuntimeError(f"{name} is not set (put it in .env — never commit it)")
    return key or None


def model_routes(cfg: dict) -> dict[str, dict]:
    """How each model is reached: {"api": "openrouter"} or {"api": "anthropic", "api_model": ...}.

    Models are always identified by their OpenRouter ID (cache keys, results), whichever API
    serves them; prices come from the OpenRouter listing, which matches first-party pricing.
    """
    return {m["id"]: {"api": m.get("api", "openrouter"), "api_model": m.get("api_model", m["id"]),
                      "providers": m.get("providers"), "max_tokens": m.get("max_tokens")}
            for m in cfg["models"]}


def token_limits(routes: dict[str, dict]) -> dict[str, int]:
    """Per-model output limits below the global one (a host's maximum, DECISIONS D16)."""
    return {m: r["max_tokens"] for m, r in routes.items() if r.get("max_tokens")}


def fetch_pricing(model_ids: list[str], client: httpx.Client | None = None) -> dict:
    """Live prices and supported parameters for ``model_ids``; saved to results/pricing.json."""
    close = client is None
    client = client or httpx.Client(timeout=60)
    try:
        resp = client.get(MODELS_URL)
        resp.raise_for_status()
        data = {m["id"]: m for m in resp.json()["data"]}
    finally:
        if close:
            client.close()
    out = {"fetched": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "models": {}}
    for mid in model_ids:
        if mid not in data:
            raise RuntimeError(f"model {mid!r} is not listed by OpenRouter")
        m = data[mid]
        out["models"][mid] = {
            "prompt": float(m["pricing"]["prompt"]),
            "completion": float(m["pricing"]["completion"]),
            "supported_parameters": m.get("supported_parameters") or [],
            "context_length": m.get("context_length"),
        }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    PRICING_PATH.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return out


# --------------------------------------------------------------------------------------
# Jobs


@dataclass(frozen=True)
class Job:
    model: str
    question_id: str
    condition: str
    repeat: int
    prompt: str

    @property
    def key(self) -> str:
        return f"{self.model}|{self.question_id}|{self.condition}|{self.repeat}"


def build_jobs(models: list[str], conditions: list[str] | None = None, question_ids: list[str] | None = None,
               repeats: bool = True) -> list[Job]:
    from .questions import META_PATH

    questions = load_questions()
    if question_ids is not None:
        wanted = set(question_ids)
        questions = [q for q in questions if q["id"] in wanted]
    repeat_ids = set(json.loads(META_PATH.read_text())["repeat_sample"]) if repeats else set()
    jobs = []
    for model in models:
        for q in questions:
            for cond in q["conditions"]:
                if conditions and cond not in conditions:
                    continue
                prompt = render_prompt(q, cond)
                jobs.append(Job(model, q["id"], cond, 0, prompt))
                if cond == "baseline" and q["id"] in repeat_ids:
                    jobs += [Job(model, q["id"], cond, r, prompt) for r in REPEATS]
    return jobs


def anthropic_body(job: Job, settings: dict, api_model: str) -> dict:
    """Messages API request. No temperature (Claude 5.x models reject non-default sampling
    values), no thinking parameter (each model's default adaptive thinking, SPEC §6), no
    system prompt, no tools."""
    return {
        "model": api_model,
        "max_tokens": settings["max_tokens"],
        "messages": [{"role": "user", "content": job.prompt}],
    }


def request_body(job: Job, settings: dict, supported: list[str], providers: list[str] | None = None) -> dict:
    body = {
        "model": job.model,
        "messages": [{"role": "user", "content": job.prompt}],
        "max_tokens": settings["max_tokens"],
        "usage": {"include": True},  # OpenRouter returns the call's cost in the response
    }
    if "temperature" in supported:
        body["temperature"] = settings["temperature"]
    if providers:
        # serve every call from the same host(s): hosts differ in quantisation (e.g. fp4)
        body["provider"] = {"order": list(providers), "allow_fallbacks": False}
    return body


# --------------------------------------------------------------------------------------
# Cache


# finish reasons meaning "stopped at max_tokens" (OpenRouter / Anthropic)
CUT_OFF = ("length", "max_tokens")

SCHEMA = """
CREATE TABLE IF NOT EXISTS calls (
    key TEXT PRIMARY KEY,
    model TEXT, question_id TEXT, condition TEXT, repeat INTEGER,
    status TEXT,                 -- ok | error
    timestamp TEXT, latency REAL, attempts INTEGER,
    request TEXT, response TEXT, -- full JSON
    content TEXT, finish_reason TEXT, served_model TEXT, provider TEXT,
    prompt_tokens INTEGER, completion_tokens INTEGER, reasoning_tokens INTEGER,
    cost REAL, error TEXT
)
"""


class Cache:
    def __init__(self, path: Path = CACHE_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute(SCHEMA)
        self.db.commit()
        if path == CACHE_PATH and self.db.execute("SELECT COUNT(*) FROM calls").fetchone()[0] == 0:
            self.import_raw()

    def import_raw(self, raw_dir: Path = RAW_DIR) -> int:
        """Fill an empty cache from the published results/raw/*.jsonl (fresh clone)."""
        n = 0
        for f in sorted(raw_dir.glob("*.jsonl")) if raw_dir.exists() else []:
            for line in f.read_text(encoding="utf-8").splitlines():
                rec = json.loads(line)
                for k in ("request", "response"):
                    rec[k] = json.dumps(rec[k], ensure_ascii=False) if rec[k] is not None else None
                self.put(rec)
                n += 1
        return n

    def get(self, key: str) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM calls WHERE key = ?", (key,)).fetchone()

    def put(self, rec: dict) -> None:
        cols = ", ".join(rec)
        marks = ", ".join("?" for _ in rec)
        self.db.execute(f"INSERT OR REPLACE INTO calls ({cols}) VALUES ({marks})", list(rec.values()))
        self.db.commit()

    def max_tokens_used(self) -> dict[str, set[int]]:
        """Per model, the max_tokens values of its successful cached requests."""
        out: dict[str, set[int]] = {}
        for model, req in self.db.execute("SELECT model, request FROM calls WHERE status = 'ok'"):
            out.setdefault(model, set()).add(json.loads(req).get("max_tokens"))
        return out

    def cut_off_below(self, max_tokens: int, per_model: dict[str, int] | None = None) -> set[str]:
        """Keys of answers that stopped at a token limit lower than the current one (DECISIONS D16).

        An answer that finished under its limit is exactly what the model would have written
        with a higher limit, so it stays; one that was cut off has to be asked again.
        """
        per_model = per_model or {}
        marks = ", ".join("?" for _ in CUT_OFF)
        rows = self.db.execute(f"SELECT key, model, request FROM calls WHERE finish_reason IN ({marks})", list(CUT_OFF))
        return {k for k, model, req in rows
                if json.loads(req).get("max_tokens", 0) < per_model.get(model, max_tokens)}

    def total_cost(self) -> float:
        return self.db.execute("SELECT COALESCE(SUM(cost), 0) FROM calls").fetchone()[0]

    def rows(self) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM calls ORDER BY key").fetchall()

    def model_averages(self, model: str) -> tuple[int, float, float]:
        """(n, mean prompt tokens, mean completion tokens) over successful calls of a model."""
        r = self.db.execute(
            "SELECT COUNT(*), AVG(prompt_tokens), AVG(completion_tokens) FROM calls "
            "WHERE model = ? AND status = 'ok' AND completion_tokens IS NOT NULL", (model,)
        ).fetchone()
        return r[0], r[1] or 0.0, r[2] or 0.0


# --------------------------------------------------------------------------------------
# Estimates


def estimate(jobs: list[Job], pricing: dict, settings: dict, cache: Cache,
             limits: dict[str, int] | None = None) -> list[dict]:
    """Per model: calls still to make, and expected / worst-case cost.

    Expected tokens come from this model's cached calls once there are >= 5 (e.g. after the dry
    run); otherwise ~4 characters per prompt token and 80 output tokens (a quote plus JSON).
    Worst case assumes every call uses the full ``max_tokens``.
    """
    out = []
    for model in dict.fromkeys(j.model for j in jobs):
        redo = cache.cut_off_below(settings["max_tokens"], limits)
        todo = [j for j in jobs if j.model == model and (cache.get(j.key) is None or j.key in redo)]
        price = pricing["models"][model]
        n_seen, avg_in, avg_out = cache.model_averages(model)
        prompt_toks = sum(len(j.prompt) / 4 + 10 for j in todo)
        if n_seen >= 5:
            exp_in, exp_out, basis = avg_in * len(todo), avg_out * len(todo), f"measured on {n_seen} calls"
        else:
            # ~350 output tokens: measured mean of thinking models in the dry run at a 2,000 limit
            exp_in, exp_out, basis = prompt_toks, 350 * len(todo), "rough guess (no calls yet)"
        worst_out = (limits or {}).get(model, settings["max_tokens"]) * len(todo)
        out.append({
            "model": model, "calls": len(todo), "basis": basis,
            "expected_cost": exp_in * price["prompt"] + exp_out * price["completion"],
            "worst_cost": prompt_toks * price["prompt"] + worst_out * price["completion"],
            "expected_tokens": int(exp_in + exp_out),
        })
    return out


# --------------------------------------------------------------------------------------
# Calling the API


class BudgetExceeded(Exception):
    pass


class Budget:
    """Reserve worst-case cost before a request; settle with the real cost after."""

    def __init__(self, spent: float, cap: float | None):
        self.spent, self.cap, self.reserved = spent, cap, 0.0
        self.stopped = False

    def reserve(self, amount: float) -> None:
        if self.cap is not None and self.spent + self.reserved + amount > self.cap:
            self.stopped = True
            raise BudgetExceeded
        self.reserved += amount

    def settle(self, reserved: float, actual: float) -> None:
        self.reserved -= reserved
        self.spent += actual


def _parse_ok(data: dict) -> dict:
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    usage = data.get("usage") or {}
    details = usage.get("completion_tokens_details") or {}
    return {
        "content": msg.get("content"),
        "finish_reason": choice.get("finish_reason") or choice.get("native_finish_reason"),
        "served_model": data.get("model"),
        "provider": data.get("provider"),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "reasoning_tokens": details.get("reasoning_tokens"),
        "cost": usage.get("cost"),
    }


async def call_one(client: httpx.AsyncClient, job: Job, body: dict, settings: dict,
                   sleep: Callable[[float], "asyncio.Future"] = asyncio.sleep) -> dict:
    """One request with retries. Returns a cache record (status ok or error)."""
    attempts, last_error = 0, ""
    started = time.monotonic()
    while attempts < settings["max_attempts"]:
        attempts += 1
        t0 = time.monotonic()
        try:
            resp = await client.post(OPENROUTER_URL, json=body, timeout=settings["timeout_seconds"])
            latency = time.monotonic() - t0
            try:
                data = resp.json()
            except ValueError:
                data = {"error": {"code": resp.status_code, "message": resp.text[:500]}}
            err = data.get("error") if isinstance(data, dict) else None
            if resp.status_code == 200 and not err and data.get("choices"):
                return {**_record_base(job, body, attempts, started), "status": "ok", "latency": latency,
                        "response": json.dumps(data, ensure_ascii=False), **_parse_ok(data), "error": None}
            code = (err or {}).get("code", resp.status_code) if isinstance(err, dict) else resp.status_code
            last_error = f"HTTP {resp.status_code}: {json.dumps(err or data)[:400]}"
            transient = resp.status_code in TRANSIENT_STATUS or code in TRANSIENT_STATUS
            if not transient:
                break
            wait = float(resp.headers.get("retry-after", 0) or 0)
        except (httpx.TimeoutException, httpx.TransportError) as e:
            last_error = f"{type(e).__name__}: {e}"
            wait = 0.0
        await sleep(max(wait, min(60.0, 2 ** attempts + random.random())))
    return {**_record_base(job, body, attempts, started), "status": "error", "latency": None,
            "response": None, "content": None, "finish_reason": None, "served_model": None,
            "provider": None, "prompt_tokens": None, "completion_tokens": None,
            "reasoning_tokens": None, "cost": 0.0, "error": last_error}


async def call_one_anthropic(client, job: Job, body: dict, price: dict) -> dict:
    """One Messages API request through the Anthropic SDK, which itself retries rate limits,
    overload and server errors with exponential backoff (``max_retries`` on the client)."""
    import anthropic

    t0 = time.monotonic()
    base = _record_base(job, {"api": "anthropic", **body}, 1, t0)
    try:
        msg = await client.messages.create(**body)
    except anthropic.APIStatusError as e:
        error = f"HTTP {e.status_code}: {e.message}"[:500]
    except anthropic.APIConnectionError as e:  # includes APITimeoutError
        error = f"{type(e).__name__}: {e}"[:500]
    else:
        latency = time.monotonic() - t0
        data = msg.to_dict()
        text = "".join(b.text for b in msg.content if b.type == "text")
        p_tok, c_tok = msg.usage.input_tokens, msg.usage.output_tokens
        return {**base, "status": "ok", "latency": latency, "response": json.dumps(data, ensure_ascii=False),
                "content": text, "finish_reason": msg.stop_reason, "served_model": msg.model,
                "provider": "Anthropic", "prompt_tokens": p_tok, "completion_tokens": c_tok,
                # usage.output_tokens includes thinking; the API does not report it separately
                "reasoning_tokens": None,
                "cost": p_tok * price["prompt"] + c_tok * price["completion"], "error": None}
    return {**base, "status": "error", "latency": None, "response": None, "content": None,
            "finish_reason": None, "served_model": None, "provider": None, "prompt_tokens": None,
            "completion_tokens": None, "reasoning_tokens": None, "cost": 0.0, "error": error}


def _record_base(job: Job, body: dict, attempts: int, started: float) -> dict:
    return {
        "key": job.key, "model": job.model, "question_id": job.question_id,
        "condition": job.condition, "repeat": job.repeat,
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "attempts": attempts, "request": json.dumps(body, ensure_ascii=False),
    }


async def run_jobs(jobs: list[Job], cache: Cache, pricing: dict, settings: dict, api_key: str | None,
                   max_cost: float | None, retry_errors: bool = False,
                   transport: httpx.AsyncBaseTransport | None = None,
                   progress: Callable[[dict], None] | None = None,
                   sleep: Callable[[float], "asyncio.Future"] = asyncio.sleep,
                   routes: dict[str, dict] | None = None, anthropic_client=None,
                   spent_before: float = 0.0) -> dict:
    """Run every job not already cached. Returns counts and spend.

    ``routes`` (from ``model_routes``) sends some models to the Anthropic API; the rest go to
    OpenRouter. ``anthropic_client`` defaults to an ``AsyncAnthropic`` built from
    ANTHROPIC_API_KEY (or the SDK's default credentials). ``spent_before`` is money spent on
    answers no longer in the cache (``archived_costs``); it counts towards ``max_cost``.
    """
    routes = routes or {}
    if anthropic_client is None and any(routes.get(j.model, {}).get("api") == "anthropic" for j in jobs):
        import anthropic

        key = load_api_key("ANTHROPIC_API_KEY", required=False)
        kwargs = {"max_retries": settings["max_attempts"] - 1, "timeout": settings["timeout_seconds"]}
        anthropic_client = anthropic.AsyncAnthropic(api_key=key, **kwargs) if key else anthropic.AsyncAnthropic(**kwargs)
    redo = cache.cut_off_below(settings["max_tokens"], token_limits(routes))
    todo = []
    for j in jobs:
        rec = cache.get(j.key)
        if rec is None or (retry_errors and rec["status"] == "error") or j.key in redo:
            todo.append(j)
    budget = Budget(cache.total_cost() + spent_before, max_cost)
    stats = {"done": 0, "errors": 0, "skipped_cached": len(jobs) - len(todo), "not_run_budget": 0}
    headers = {"Authorization": f"Bearer {api_key}", "X-Title": "QuoteBench"}
    sems: dict[str, asyncio.Semaphore] = {}

    n_models = len({j.model for j in todo}) or 1
    limits = httpx.Limits(max_connections=settings["concurrency"] * n_models + 10,
                          max_keepalive_connections=settings["concurrency"] * n_models)
    async with httpx.AsyncClient(headers=headers, transport=transport, limits=limits) as client:
        async def worker(job: Job) -> None:
            sem = sems.setdefault(job.model, asyncio.Semaphore(settings["concurrency"]))
            async with sem:
                if budget.stopped:
                    stats["not_run_budget"] += 1
                    return
                price = pricing["models"][job.model]
                route = routes.get(job.model, {"api": "openrouter"})
                s = {**settings, "max_tokens": route.get("max_tokens") or settings["max_tokens"]}
                worst = (len(job.prompt) / 3 + 20) * price["prompt"] + s["max_tokens"] * price["completion"]
                try:
                    budget.reserve(worst)
                except BudgetExceeded:
                    stats["not_run_budget"] += 1
                    return
                if route["api"] == "anthropic":
                    body = anthropic_body(job, s, route["api_model"])
                    rec = await call_one_anthropic(anthropic_client, job, body, price)
                else:
                    body = request_body(job, s, price["supported_parameters"], route.get("providers"))
                    rec = await call_one(client, job, body, s, sleep=sleep)
                if rec["status"] == "ok" and rec["cost"] is None:
                    rec["cost"] = (rec["prompt_tokens"] or 0) * price["prompt"] + (rec["completion_tokens"] or 0) * price["completion"]
                budget.settle(worst, rec["cost"] or 0.0)
                cache.put(rec)
                stats["done"] += 1
                stats["errors"] += rec["status"] == "error"
                if progress:
                    progress({**stats, "spent": budget.spent, "last": job.key})

        await asyncio.gather(*(worker(j) for j in todo))
    stats["spent_total"] = budget.spent
    stats["budget_stopped"] = budget.stopped
    return stats


# --------------------------------------------------------------------------------------
# Export


ARCHIVE_DIR = ROOT / "results" / "archive"


def archived_costs(archive_dir: Path = ARCHIVE_DIR) -> dict[str, float]:
    """Per model, what replaced or discarded answers (dry runs, cut-off answers) cost.

    Those answers are no longer in the cache, but the money was spent: it counts towards
    ``--max-cost`` and the reported spend.
    """
    out: dict[str, float] = {}
    for f in sorted(archive_dir.rglob("*.jsonl")) if archive_dir.exists() else []:
        for line in f.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            out[rec["model"]] = out.get(rec["model"], 0.0) + (rec.get("cost") or 0.0)
    return out


def archive_cut_off(cache: Cache, max_tokens: int, out_dir: Path,
                    per_model: dict[str, int] | None = None) -> list[Path]:
    """Before re-asking, keep the cut-off answers in ``out_dir/<model>.jsonl`` for the record."""
    keys = cache.cut_off_below(max_tokens, per_model)
    by_model: dict[str, list[dict]] = {}
    for row in cache.rows():
        if row["key"] in keys:
            rec = dict(row)
            for k in ("request", "response"):
                rec[k] = json.loads(rec[k]) if rec[k] else None
            by_model.setdefault(rec["model"], []).append(rec)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for model, recs in by_model.items():
        path = out_dir / (model.replace("/", "__") + ".jsonl")
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs), encoding="utf-8")
        paths.append(path)
    return paths


def export_raw(cache: Cache) -> list[Path]:
    """Write every cached call to results/raw/<model>.jsonl (sorted, one record per line)."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    by_model: dict[str, list[dict]] = {}
    for row in cache.rows():
        rec = dict(row)
        for k in ("request", "response"):
            rec[k] = json.loads(rec[k]) if rec[k] else None
        by_model.setdefault(rec["model"], []).append(rec)
    paths = []
    for model, recs in by_model.items():
        path = RAW_DIR / (model.replace("/", "__") + ".jsonl")
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs), encoding="utf-8")
        paths.append(path)
    return paths

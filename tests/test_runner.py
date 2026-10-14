"""Runner tests against a fake OpenRouter (httpx.MockTransport): no network, no spending."""

import asyncio
import json

import httpx
import pytest

from quotebench import runner as R

SETTINGS = {"temperature": 0, "max_tokens": 400, "concurrency": 4, "max_attempts": 4, "timeout_seconds": 5}
PRICING = {"models": {
    "fake/with-temp": {"prompt": 1e-6, "completion": 5e-6, "supported_parameters": ["temperature", "max_tokens"]},
    "fake/no-temp": {"prompt": 1e-6, "completion": 5e-6, "supported_parameters": ["max_tokens", "reasoning"]},
}}


def ok_response(body, content='{"quote": "In the beginning", "location": "", "cannot_quote": false}'):
    return httpx.Response(200, json={
        "id": "gen-1", "model": body["model"], "provider": "FakeProvider",
        "choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "cost": 0.00035,
                  "completion_tokens_details": {"reasoning_tokens": 0}},
    })


class FakeOpenRouter:
    def __init__(self, script=None):
        self.calls = []
        self.script = list(script or [])

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.calls.append(body)
        if self.script:
            step = self.script.pop(0)
            if step is not None:
                return step
        return ok_response(body)


def run(jobs, cache, fake, cap=10.0, retry_errors=False):
    async def no_sleep(_):
        return None
    return asyncio.run(R.run_jobs(jobs, cache, PRICING, SETTINGS, "sk-test", cap, retry_errors=retry_errors,
                                  transport=httpx.MockTransport(fake), sleep=no_sleep))


@pytest.fixture
def cache(tmp_path):
    return R.Cache(tmp_path / "cache.sqlite")


def jobs_for(model, n=3):
    return R.build_jobs([model], ["baseline"], ["t1-kjv-0001", "t1-kjv-0002", "t1-kjv-0003"][:n], repeats=False)


def test_records_everything_and_resumes_without_paying_twice(cache):
    fake = FakeOpenRouter()
    jobs = jobs_for("fake/with-temp")
    stats = run(jobs, cache, fake)
    assert stats["done"] == 3 and stats["errors"] == 0 and len(fake.calls) == 3
    rec = cache.get(jobs[0].key)
    assert rec["status"] == "ok" and rec["prompt_tokens"] == 100 and rec["completion_tokens"] == 50
    assert rec["cost"] == pytest.approx(0.00035) and rec["finish_reason"] == "stop"
    assert json.loads(rec["request"])["messages"][0]["content"] == jobs[0].prompt
    assert json.loads(rec["response"])["provider"] == "FakeProvider"
    # second run: everything cached, no new calls
    stats = run(jobs, cache, fake)
    assert stats["done"] == 0 and stats["skipped_cached"] == 3 and len(fake.calls) == 3


def test_request_body_settings():
    job = jobs_for("fake/with-temp", 1)[0]
    body = R.request_body(job, SETTINGS, PRICING["models"]["fake/with-temp"]["supported_parameters"])
    assert body["temperature"] == 0 and body["max_tokens"] == 400
    assert body["messages"] == [{"role": "user", "content": job.prompt}]  # no system prompt
    assert "tools" not in body and "plugins" not in body and "reasoning" not in body
    body = R.request_body(job, SETTINGS, PRICING["models"]["fake/no-temp"]["supported_parameters"])
    assert "temperature" not in body and "provider" not in body
    body = R.request_body(job, SETTINGS, [], ["deepseek"])
    assert body["provider"] == {"order": ["deepseek"], "allow_fallbacks": False}


def test_retries_rate_limits_then_succeeds(cache):
    fake = FakeOpenRouter([httpx.Response(429, json={"error": {"code": 429, "message": "slow down"}}),
                           httpx.Response(502, text="bad gateway")])
    jobs = jobs_for("fake/with-temp", 1)
    stats = run(jobs, cache, fake)
    rec = cache.get(jobs[0].key)
    assert rec["status"] == "ok" and rec["attempts"] == 3 and stats["errors"] == 0


def test_permanent_error_is_error_not_wrong_answer(cache):
    from quotebench.questions import load_questions
    from quotebench.scoring import ERROR, score_answer

    fake = FakeOpenRouter([httpx.Response(400, json={"error": {"code": 400, "message": "bad model"}})])
    jobs = jobs_for("fake/with-temp", 1)
    stats = run(jobs, cache, fake)
    rec = cache.get(jobs[0].key)
    assert rec["status"] == "error" and rec["attempts"] == 1 and stats["errors"] == 1
    q = next(q for q in load_questions() if q["id"] == jobs[0].question_id)
    assert score_answer(q, rec["content"], error=rec["error"])["label"] == ERROR
    # errors are not retried unless asked
    assert run(jobs, cache, fake)["done"] == 0
    assert run(jobs, cache, fake, retry_errors=True)["done"] == 1
    assert cache.get(jobs[0].key)["status"] == "ok"


def test_retries_give_up_after_max_attempts(cache):
    fake = FakeOpenRouter([httpx.Response(503, text="down")] * 10)
    jobs = jobs_for("fake/with-temp", 1)
    run(jobs, cache, fake)
    rec = cache.get(jobs[0].key)
    assert rec["status"] == "error" and rec["attempts"] == SETTINGS["max_attempts"]


def test_budget_cap_is_never_exceeded(cache):
    fake = FakeOpenRouter()
    jobs = jobs_for("fake/with-temp", 3)
    # Each call reserves its worst case (~$0.0021: 400 output tokens) and really costs $0.00035.
    # With a $0.0026 cap: call 1 and 2 fit (0.00035 spent + 0.0021 reserved < 0.0026), call 3
    # does not (0.0007 + 0.0021 > 0.0026), even though its real cost would have fitted.
    stats = run(jobs, cache, fake, cap=0.0026)
    assert stats["budget_stopped"] and stats["not_run_budget"] == 1
    assert stats["done"] == len(fake.calls) == 2
    assert cache.total_cost() <= 0.0026


def test_estimate_uses_measured_tokens(cache):
    fake = FakeOpenRouter()
    measured = R.build_jobs(["fake/with-temp"], ["baseline"], [f"t1-kjv-{i:04d}" for i in range(1, 7)], repeats=False)
    run(measured, cache, fake)
    more = R.build_jobs(["fake/with-temp"], ["baseline"], [f"t1-kjv-{i:04d}" for i in range(1, 11)], repeats=False)
    [row] = R.estimate(more, PRICING, SETTINGS, cache)
    assert row["calls"] == 4 and "measured on 6" in row["basis"]
    assert row["expected_cost"] == pytest.approx(4 * (100 * 1e-6 + 50 * 5e-6))
    assert row["worst_cost"] > row["expected_cost"]


def test_repeat_sample_jobs():
    jobs = R.build_jobs(["fake/with-temp"])
    base = [j for j in jobs if j.repeat == 0]
    reps = [j for j in jobs if j.repeat > 0]
    assert len(base) == 1710 and len(reps) == 70 * 3
    assert {j.condition for j in reps} == {"baseline"}


# --- Anthropic API route (fake SDK client) ---------------------------------------------------

from types import SimpleNamespace


class FakeMessage:
    def __init__(self, model, text, stop_reason="end_turn"):
        self.model, self.stop_reason = model, stop_reason
        self.content = [SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)]
        self.usage = SimpleNamespace(input_tokens=120, output_tokens=80)

    def to_dict(self):
        return {"model": self.model, "stop_reason": self.stop_reason,
                "content": [{"type": "thinking", "thinking": ""}, {"type": "text", "text": self.content[1].text}],
                "usage": {"input_tokens": 120, "output_tokens": 80}}


class FakeAnthropic:
    def __init__(self, fail_with=None):
        self.messages, self.calls, self.fail_with = self, [], fail_with

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail_with is not None:
            raise self.fail_with
        return FakeMessage(kwargs["model"], '{"quote": "In the beginning", "location": "", "cannot_quote": false}')


ROUTES = {"fake/no-temp": {"api": "anthropic", "api_model": "claude-fake-1"},
          "fake/with-temp": {"api": "openrouter", "api_model": "fake/with-temp"}}


def run_routed(jobs, cache, fake_or, fake_anthropic, cap=10.0):
    async def no_sleep(_):
        return None
    return asyncio.run(R.run_jobs(jobs, cache, PRICING, SETTINGS, "sk-test", cap,
                                  transport=httpx.MockTransport(fake_or), sleep=no_sleep,
                                  routes=ROUTES, anthropic_client=fake_anthropic))


def test_anthropic_route(cache):
    fake_or, fake_an = FakeOpenRouter(), FakeAnthropic()
    jobs = jobs_for("fake/no-temp", 2) + jobs_for("fake/with-temp", 1)
    stats = run_routed(jobs, cache, fake_or, fake_an)
    assert stats["done"] == 3 and len(fake_an.calls) == 2 and len(fake_or.calls) == 1
    sent = fake_an.calls[0]
    assert sent == {"model": "claude-fake-1", "max_tokens": 400,
                    "messages": [{"role": "user", "content": jobs[0].prompt}]}  # no temperature/thinking/tools
    rec = cache.get(jobs[0].key)
    assert rec["status"] == "ok" and rec["provider"] == "Anthropic" and rec["finish_reason"] == "end_turn"
    assert rec["content"].startswith('{"quote"')
    assert rec["cost"] == pytest.approx(120 * 1e-6 + 80 * 5e-6)
    assert json.loads(rec["request"])["api"] == "anthropic"


def test_anthropic_errors_are_recorded(cache):
    import anthropic
    import httpx2

    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    err = anthropic.BadRequestError("bad request", response=httpx2.Response(400, request=req), body=None)
    jobs = jobs_for("fake/no-temp", 1)
    stats = run_routed(jobs, cache, FakeOpenRouter(), FakeAnthropic(fail_with=err))
    rec = cache.get(jobs[0].key)
    assert stats["errors"] == 1 and rec["status"] == "error" and rec["error"].startswith("HTTP 400")
    conn = anthropic.APIConnectionError(request=req)
    jobs2 = jobs_for("fake/no-temp", 2)[1:]
    run_routed(jobs2, cache, FakeOpenRouter(), FakeAnthropic(fail_with=conn))
    assert cache.get(jobs2[0].key)["error"].startswith("APIConnectionError")


def cut_off_response(body):
    return httpx.Response(200, json={
        "id": "gen-2", "model": body["model"], "provider": "FakeProvider",
        "choices": [{"message": {"role": "assistant", "content": ""}, "finish_reason": "length"}],
        "usage": {"prompt_tokens": 100, "completion_tokens": body["max_tokens"], "cost": 0.002,
                  "completion_tokens_details": {"reasoning_tokens": body["max_tokens"]}},
    })


def test_raising_the_limit_reasks_only_cut_off_answers(cache, tmp_path):
    jobs = jobs_for("fake/with-temp")
    fake = FakeOpenRouter([None, cut_off_response({"model": "fake/with-temp", "max_tokens": 400}), None])
    run(jobs, cache, fake)
    assert cache.cut_off_below(400) == set()               # same limit: nothing to redo
    assert cache.cut_off_below(4000) == {jobs[1].key}       # higher limit: only the cut-off one
    old = R.archive_cut_off(cache, 4000, tmp_path / "archive")
    assert len(old) == 1 and json.loads(old[0].read_text())["finish_reason"] == "length"

    fake2 = FakeOpenRouter()
    async def no_sleep(_):
        return None
    stats = asyncio.run(R.run_jobs(jobs, cache, PRICING, {**SETTINGS, "max_tokens": 4000}, "sk-test", 10.0,
                                   transport=httpx.MockTransport(fake2), sleep=no_sleep))
    assert stats["done"] == 1 and len(fake2.calls) == 1 and fake2.calls[0]["max_tokens"] == 4000
    assert cache.get(jobs[1].key)["finish_reason"] == "stop"
    assert cache.cut_off_below(4000) == set()
    # the two answers that finished under 400 tokens are kept as they were
    assert {json.loads(cache.get(j.key)["request"])["max_tokens"] for j in jobs} == {400, 4000}


def test_per_model_limit_for_hosts_with_a_lower_maximum(cache):
    jobs = jobs_for("fake/with-temp", n=1)
    run(jobs, cache, FakeOpenRouter([cut_off_response({"model": "fake/with-temp", "max_tokens": 400})]))
    assert cache.cut_off_below(16000, {"fake/with-temp": 400}) == set()
    assert cache.cut_off_below(16000, {"fake/with-temp": 800}) == {jobs[0].key}
    fake = FakeOpenRouter()
    async def no_sleep(_):
        return None
    routes = {"fake/with-temp": {"api": "openrouter", "max_tokens": 800}}
    asyncio.run(R.run_jobs(jobs, cache, PRICING, {**SETTINGS, "max_tokens": 16000}, "sk-test", 10.0,
                           transport=httpx.MockTransport(fake), sleep=no_sleep, routes=routes))
    assert [c["max_tokens"] for c in fake.calls] == [800]
    assert cache.max_tokens_used() == {"fake/with-temp": {800}}


def test_replaced_answers_still_count_towards_the_cap(cache, tmp_path):
    arch = tmp_path / "archive" / "old"
    arch.mkdir(parents=True)
    (arch / "m.jsonl").write_text(json.dumps({"model": "fake/with-temp", "cost": 9.999}) + "\n")
    spent = sum(R.archived_costs(tmp_path / "archive").values())
    assert spent == 9.999
    async def no_sleep(_):
        return None
    stats = asyncio.run(R.run_jobs(jobs_for("fake/with-temp"), cache, PRICING, SETTINGS, "sk-test", 10.0,
                                   transport=httpx.MockTransport(FakeOpenRouter()), sleep=no_sleep,
                                   spent_before=spent))
    assert stats["budget_stopped"] and stats["spent_total"] <= 10.0

"""Client-side latency of a deployed backend: /health, /me and chat turns (CO6, Day 17).

    $env:RAG_LATENCY_TOKEN = "<a demo account's JWT>"      # never printed, never on the command line
    python -m scripts.measure_latency --base-url https://rag-study-assistant-api.onrender.com
    Remove-Item Env:RAG_LATENCY_TOKEN

Method (the Day 14 brief's, Decision 3A, kept so the numbers compare):
- One warm-up /health, /me and chat turn first, all discarded: Render's free plan spins down, and the
  first request after that pays for the cold start.
- n x /health and n x /me, one after another. median(/me) - median(/health) approximates the
  server-side cost of auth + its database round trips, since the client-to-Render leg is in both.
- n chat turns, each a **different question**: a repeated one would be replayed from the semantic
  cache (CO5) and measure Redis instead of the pipeline. A replay is still detected (the replayed
  stream is the one sent with Cache-Control: no-cache) and left out of the statistics.
- Per chat turn: time to the first `metadata` frame (everything before the stream starts: guards,
  the turn's first transaction, retrieval, prompt — where CO6's round trips show) and to `[DONE]`.
- All turns go to one chat session, created by the warm-up turn, so no turn pays for topic
  tagging (an extra LLM call that runs only while a session's topic is still "General").

Medians and p90s, because network jitter is long-tailed. Stdlib + httpx only, and no import of `app`,
so it runs from any shell without the backend's settings. Every chat turn spends the account's
Gemini free-tier quota (one answer + its embeddings): use a demo account and the default n.
"""
import argparse
import json
import logging
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import httpx

# Not under "rag_assistant": this script never imports the app, and once something has (a test run),
# setup_logging() stops "rag_assistant" propagating, so a child logger would only reach app.log.
logger = logging.getLogger("measure_latency")

TOKEN_ENV = "RAG_LATENCY_TOKEN"
TIMEOUT_SECONDS = 120.0

WARMUP_QUESTION = "What is the difference between a process and a thread?"
# Distinct, unrelated topics, so no question is close enough to another to hit the semantic cache.
QUESTIONS = [
    "How does photosynthesis convert light into chemical energy?",
    "What causes the seasons on Earth?",
    "Explain how a binary search tree keeps its keys ordered.",
    "What is the Krebs cycle and where does it happen in the cell?",
    "How do vaccines train the immune system?",
    "What is opportunity cost in economics?",
    "How does TCP congestion control react to packet loss?",
    "What were the main causes of the French Revolution?",
    "How does a transistor work as a switch?",
    "What is the difference between mitosis and meiosis?",
    "Explain Newton's third law with an everyday example.",
    "What is a hash function and why do hash tables need one?",
    "How do plate tectonics create mountains?",
    "What does the derivative of a function measure?",
    "How does supply and demand set a market price?",
    "What is the role of the mitochondria's inner membrane?",
    "How does public-key cryptography let strangers communicate securely?",
    "What is the greenhouse effect?",
    "Explain recursion with the factorial function.",
    "How do neurons transmit signals across a synapse?",
]


@dataclass
class ChatSample:
    to_metadata_ms: Optional[float] = None
    total_ms: Optional[float] = None
    replayed: bool = False
    session_id: Optional[int] = None
    problem: Optional[str] = None


@dataclass
class Results:
    health_ms: List[float] = field(default_factory=list)
    me_ms: List[float] = field(default_factory=list)
    chats: List[ChatSample] = field(default_factory=list)


def p90(values: List[float]) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(0.9 * (len(ordered) - 1)))]


def timed_get(client: httpx.Client, path: str, headers: Dict[str, str]) -> float:
    started = time.perf_counter()
    response = client.get(path, headers=headers)
    elapsed = (time.perf_counter() - started) * 1000
    if response.status_code != 200:
        raise RuntimeError(f"GET {path} returned {response.status_code}")
    return elapsed


def chat_turn(client: httpx.Client, token: str, question: str, session_id: int) -> ChatSample:
    """One /chat/stream turn. Errors are reported by type and status only: the URL holds the token.

    The stream is always read to its end, never left at [DONE]: httpx returns a connection to the
    pool only after the whole body is read, and closes it otherwise, so an early `break` made every
    later request reconnect (measured Day 17: +2.05 s per turn on Windows' localhost; on Render a new
    TLS handshake). Timing still stops at [DONE].
    """
    sample = ChatSample()
    params: Dict[str, str | int] = {"query": question, "session_id": session_id, "mode": "quick", "token": token}
    started = time.perf_counter()
    try:
        with client.stream("GET", "/chat/stream", params=params) as response:
            if response.status_code != 200:
                sample.problem = f"status {response.status_code}"
                response.read()
                return sample
            sample.replayed = response.headers.get("cache-control", "").lower() == "no-cache"
            for line in response.iter_lines():
                if not line.startswith("data: ") or sample.total_ms is not None or sample.problem:
                    continue  # after [DONE] or an error frame: keep reading, record nothing
                payload = line[len("data: "):]
                if payload == "[DONE]":
                    sample.total_ms = (time.perf_counter() - started) * 1000
                    continue
                frame = json.loads(payload)
                if frame.get("type") == "metadata" and sample.to_metadata_ms is None:
                    sample.to_metadata_ms = (time.perf_counter() - started) * 1000
                    sample.session_id = frame.get("data", {}).get("session_id")
                elif frame.get("type") == "error":
                    sample.problem = "error frame in the stream"
    except httpx.HTTPError as error:
        sample.problem = type(error).__name__
    except json.JSONDecodeError:
        sample.problem = "unparseable frame"
    if sample.total_ms is None and sample.problem is None:
        sample.problem = "stream ended without [DONE]"
    return sample


def measure(base_url: str, token: str, n_light: int, n_chat: int) -> Results:
    results = Results()
    auth = {"Authorization": f"Bearer {token}"}
    with httpx.Client(base_url=base_url, timeout=TIMEOUT_SECONDS) as client:
        logger.info("Warm-up (discarded) ...")
        timed_get(client, "/health", {})
        timed_get(client, "/me", auth)
        warmup = chat_turn(client, token, WARMUP_QUESTION, 0)
        if warmup.problem or warmup.session_id is None:
            raise RuntimeError(f"warm-up chat turn failed: {warmup.problem or 'no session id'}")
        session_id = warmup.session_id

        for _ in range(n_light):
            results.health_ms.append(timed_get(client, "/health", {}))
        for _ in range(n_light):
            results.me_ms.append(timed_get(client, "/me", auth))
        logger.info("/health and /me: %d each", n_light)

        for i, question in enumerate(QUESTIONS[:n_chat], 1):
            sample = chat_turn(client, token, question, session_id)
            results.chats.append(sample)
            status = sample.problem or ("REPLAYED from the semantic cache" if sample.replayed else "ok")
            logger.info(
                "chat %2d/%d: metadata %s ms, total %s ms (%s)", i, n_chat,
                f"{sample.to_metadata_ms:.0f}" if sample.to_metadata_ms else "-",
                f"{sample.total_ms:.0f}" if sample.total_ms else "-", status,
            )
    return results


def row(name: str, values: List[float]) -> str:
    if not values:
        return f"| {name} (n = 0) | - | - |"
    return f"| {name} (n = {len(values)}) | {statistics.median(values):.1f} | {p90(values):.1f} |"


def report(results: Results) -> None:
    fresh = [c for c in results.chats if c.problem is None and not c.replayed]
    replayed = sum(1 for c in results.chats if c.replayed)
    failed = [c.problem for c in results.chats if c.problem]
    lines = [
        "",
        "| Metric | p50 ms | p90 ms |",
        "|---|---|---|",
        row("/health", results.health_ms),
        row("/me", results.me_ms),
    ]
    if results.health_ms and results.me_ms:
        diff = statistics.median(results.me_ms) - statistics.median(results.health_ms)
        lines.append(f"| /me - /health (p50) | {diff:.1f} | |")
    lines += [
        row("chat -> metadata", [c.to_metadata_ms for c in fresh if c.to_metadata_ms is not None]),
        row("chat -> [DONE]", [c.total_ms for c in fresh if c.total_ms is not None]),
        "",
        f"Chat turns: {len(fresh)} fresh, {replayed} replayed from the semantic cache (excluded), "
        f"{len(failed)} failed{': ' + ', '.join(failed) if failed else ''}.",
    ]
    logger.info("\n".join(lines))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", required=True, help="e.g. https://rag-study-assistant-api.onrender.com")
    parser.add_argument("--n", type=int, default=30, help="/health and /me samples each (default 30)")
    parser.add_argument("--chat", type=int, default=15, help=f"chat turns, at most {len(QUESTIONS)} (default 15)")
    args = parser.parse_args(argv)

    # stdout, not stderr: the report is the script's output (`> latency.md` keeps it).
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    # httpx logs every request URL at INFO, and a chat URL carries ?token=.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    token = os.environ.get(TOKEN_ENV, "")
    if not token:
        logger.error("Set %s to a demo account's token first (it is never printed).", TOKEN_ENV)
        return 2
    if not 1 <= args.chat <= len(QUESTIONS):
        logger.error("--chat must be between 1 and %d (each turn needs its own question)", len(QUESTIONS))
        return 2

    try:
        results = measure(args.base_url.rstrip("/"), token, args.n, args.chat)
    except (RuntimeError, httpx.HTTPError) as error:
        # str(error) of an httpx error can include the request URL, so only the type is shown for those.
        logger.error("Stopped: %s", error if isinstance(error, RuntimeError) else type(error).__name__)
        return 1
    report(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())

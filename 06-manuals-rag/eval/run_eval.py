"""Ask the live API every question in questions.json and score the answers.

Usage (the workflow sets these from 'terraform output'):
  API_URL=https://....execute-api.eu-west-2.amazonaws.com/v1 API_KEY=... python eval/run_eval.py
Exits 1 if the scores are below the gate in scoring.py.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scoring import GATE, score_case, summarise  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def ask(url: str, key: str, question: str, attempts: int = 4) -> dict:
    data = json.dumps({"question": question}).encode()
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(url, data=data, method="POST",
                                         headers={"Content-Type": "application/json", "x-api-key": key})
        try:
            with urllib.request.urlopen(request, timeout=35) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            if e.code in (429, 500, 502, 503, 504) and attempt < attempts:
                print(f"   HTTP {e.code} ({body[:80]}); retrying in {3 * attempt} s")
                time.sleep(3 * attempt)
                continue
            raise SystemExit(f"HTTP {e.code} for {question!r}: {body}")
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < attempts:
                time.sleep(3 * attempt)
                continue
            raise SystemExit(f"Could not reach the API: {e}")


def main() -> int:
    url = os.environ["API_URL"].rstrip("/") + "/ask"
    key = os.environ["API_KEY"]
    cases = json.load(open(os.path.join(HERE, "questions.json")))

    scored = []
    for n, case in enumerate(cases, start=1):
        response = ask(url, key, case["question"])
        result = score_case(case, response)
        scored.append(result)
        marks = " ".join(f"{k}={'✔' if v else '✘'}" for k, v in result.items())
        print(f"\nQ{n}. {case['question']}\n    {marks}  ({response['timings_ms']['total']:.0f} ms)")
        print(f"    A: {response.get('answer', '')[:300]}")
        for c in response.get("citations", []):
            print(f"       [{c['ref']}] {c['source']} | {c['section']} (similarity {c['score']})")
        for w in response.get("warnings", []):
            print(f"       warning: {w}")
        time.sleep(0.6)  # stay inside the API's 2 requests/second limit

    summary = summarise(scored)
    print("\n=== Evaluation summary ===")
    for measure, rate in summary["rates"].items():
        print(f"  {measure:9} {rate:>6}   (gate {GATE[measure]})")
    print("  RESULT:", "PASSED" if summary["passed"] else "FAILED: " + "; ".join(summary["failures"]))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())

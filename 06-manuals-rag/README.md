# 06 · Ask the manuals (RAG with cited sources)

Question answering over equipment maintenance manuals. Every answer comes only from the manuals, cites the manual and section it used, and says "I can't find this in the maintenance manuals" instead of guessing.

```
INDEXING (when a manual is added, changed or removed)
 s3://…/manuals/*.md ──S3 event──► indexer Lambda: split into sections → Titan embeddings (Bedrock)
                                   → FAISS index → s3://…/index/<build>/ + manifest.json (written last)

ASKING
 POST /ask {"question"} ─► API Gateway (API key, 2 req/s, 300/day) ─► query Lambda:
   embed question → FAISS: 4 nearest chunks → Mistral (Bedrock) answers from those only
   → citation check → {"answer", "citations", "sources", "timings_ms"}
```

## Example

```bash
curl -s -X POST "$ASK_URL" -H "x-api-key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"question": "What torque should the P-200 bearing housing bolts be tightened to?"}'
```
```json
{
  "found": true,
  "answer": "Tighten the bearing housing bolts to 45 Nm in a cross pattern, in two stages (first 20 Nm, then 45 Nm) [S1].",
  "citations": [{"ref": "S1", "source": "p200-centrifugal-pump", "section": "6.3 Bearing housing", "score": 0.71}],
  "sources": ["… all 4 retrieved chunks with similarity scores …"],
  "timings_ms": {"index_load": 0.1, "embed": 95, "search": 0.2, "generate": 1400, "total": 1500}
}
```
(Illustrative; your scores and timings will differ.)

## Evaluation

`eval/questions.json` holds 12 questions with known answers: 10 with the expected manual section and key fact, and 2 the manuals can't answer. `eval/run_eval.py` asks the live API and scores:

| Measure | Question it answers | Gate |
|---|---|---|
| retrieval | Was the right section among the 4 retrieved chunks? | ≥ 0.8 |
| citation | Did the answer cite that section? | ≥ 0.7 |
| fact | Does the answer contain the key fact (e.g. "45 Nm")? | ≥ 0.7 |
| refusal | For unanswerable questions, did it refuse rather than invent? | ≥ 0.5 |

The questions include traps: two different "bolt torque" questions for two machines (45 Nm vs 85 Nm), and paraphrases with no shared keywords ("my compressor keeps overheating" → *High discharge temperature*).

Results from my run: _fill in_

## Design choices

- **Chunk by manual section**, with title and section prepended before embedding, so similar text in different manuals stays distinguishable; long sections split on paragraphs with one paragraph of overlap.
- **Exact search (FAISS IndexFlatIP on normalised vectors = cosine similarity).** Microseconds for thousands of chunks; switch to HNSW or IVF for millions.
- **Index published atomically:** each build gets its own folder and `manifest.json` is written last, so a question never meets a half-written index. The question Lambda caches the index and re-checks the manifest at most once a minute.
- **Concurrent uploads are safe:** each upload starts an indexer run; a run publishes only if the manuals didn't change while it worked.
- **Grounding:** temperature 0, "only from sources" prompt, a fixed `NOT_FOUND` reply, and citation validation (invented `[S7]` references are removed and flagged; uncited answers are flagged).
- **Guards against a model mismatch:** the question Lambda refuses an index built with a different embedding model.
- **Cost controls:** API key, 2 req/s and 300 requests/day; no always-on vector database.
- **Least privilege:** the indexer can read manuals and write only `index/`; the question Lambda can only read `index/`; each can call only its Bedrock models.

## Why not Bedrock Knowledge Bases?

Knowledge Bases does chunking, embedding, storage and retrieval as a managed service. This project builds those parts by hand to make each one visible and testable. In production, Knowledge Bases is a strong option when you want managed ingestion and connectors; a hand-built pipeline suits tight control over chunking, prompts and evaluation, or a very small budget.

## Run it

Actions → **manuals-rag** → Run workflow → **apply** (build image → deploy → upload manuals → wait for the index → evaluation), then **evaluate** to re-run the questions, then **destroy**.

## Test locally

```bash
pip install -r requirements-dev.txt
python -m pytest -v
```

The tests replace Bedrock with a word-counting stand-in and S3 with an in-memory fake, covering chunking, the index, prompts and citation checks, both Lambda handlers, concurrent indexing, and scoring.

## Cost

| Item | Approx. cost |
|---|---|
| Titan embeddings for all manuals (~35 chunks) | A tiny fraction of 1p per re-index |
| One question (embedding + answer) | Well under 1p |
| Lambda, API Gateway, S3, ECR | Free allowance / pennies |

Actual cost on my bill: _fill in_

## What went wrong and how I fixed it

_Fill in._

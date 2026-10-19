# Recommendation evaluation protocol

This directory defines a small, reproducible evaluation for this application's five fictional catalog entries. It is not an industry benchmark or evidence that the product beats other recommendation systems. The fixture was authored by an evaluation agent before inspecting real model predictions. Its relevance judgments are **assistant-authored, synthetic and not human reviewed**. No actual participant text, identities, sessions, budgets or payment records belong here.

## Freeze the data before inference

`recommendation_cases.json` contains the exact seed titles, descriptions and metadata, 30 English queries, explicit graded labels, negation cases, out-of-domain requests and independent artificial group matrices. Missing relevance IDs mean grade zero. A high relevance label says the catalog supports a requested experience; it does not say the experience is available, affordable, safe for a specific person or approved by a group.

Ten development cases cover science-fiction/cyberpunk target intents and one unsupported restaurant intent. Twenty evaluation cases cover drama, paddling, hiking, generic cinema/outdoors and four other unsupported intents. Paraphrases of the same target intent remain together. This prevents paraphrase leakage across splits, but both splits still use the same tiny known catalog. It does not establish out-of-catalog generalization. Excluded entities mentioned inside a request do not change its target intent family.

Before running models, record the fixture's SHA-256, Git commit and any uncommitted source diff. Keep the JSON unchanged for a comparison. Select model, thresholds and fusion settings using development cases only. If results lead to changes, report those as development iterations; do not keep relabeling the same evaluation set as unseen. Additional human-reviewed queries should become a separately versioned evaluation set. A team member should review the labels without seeing rankings before submission.

## Compare the same task

At minimum run these baselines on identical catalog text and query lists:

1. The browser keyword token/substring policy applied to the exact server-format documents. This is labeled `keyword_server_documents`; it is not identical to browser document formatting.
2. Raw normalized MiniLM embeddings with cosine ranking.
3. A second compact embedding model, if its pinned runtime/artifacts can actually execute.
4. The proposed group aggregation, compared with average similarity and max-min utility on the same feasible candidates and member embeddings.

Server-native model comparisons use LocalEncoder.describe (title/description/domain/genre); the separate browser worker uses a different document template and is not measured here. Server model comparisons use the exact production document formatting, query prefixes and pooling/normalization. Record any model-specific prefix: omitting a required query prefix is not a fair model comparison. Do not use different descriptions, extra synonyms or labels for one method. Report a canonical query-to-ID tie-break so zero-score keyword cases cannot change between runs. Sorting by an arbitrary ID is not an abstention.

Only a successful forward pass through downloaded model weights is real-model evidence. Mock vectors exercise integration, not semantic quality. Native Python/Node ONNX results can establish those runtimes' inference and ranking; they do **not** establish browser WASM performance, responsive rendering, download compatibility or the exact behavior of a different runtime/version. No API key is needed for local embedding inference, but initial asset downloads need network access.

## Ranking and abstention metrics

Use all answerable cases in the selected split, including requests with negation. Publish their individual rankings alongside aggregate values so broad-intent queries cannot hide a failed specific request.

- **nDCG@3:** `DCG = sum((2^grade - 1) / log2(rank + 1))` at one-based ranks 1 through 3; divide by the ideal DCG from the complete fixed catalog. Empty output on an answerable query scores zero. Exclude unanswerable queries from this metric and report their count separately.
- **MRR@3:** reciprocal of the first rank through 3 with relevance grade at least 2; zero if absent. Grade 1 is a weak related alternative and is not a successful answer.
- **Top1Relevant:** fraction of answerable queries whose first result has grade at least 2. Report the denominator.
- **Answer coverage:** fraction of answerable queries receiving at least one result, reported alongside Top1Relevant. Returning everything can raise coverage while reducing quality.
- **Unsupported-request abstention:** fraction of out-of-domain cases receiving no recommended result. Also report the number answered incorrectly. Similarity is not a calibrated probability; do not label a threshold as confidence or promise OOD rejection without measuring it.
- **Negation violation@1:** fraction of explicit exclusion cases whose first result is in that case's `excluded` list. This is an evaluation signal, not proof that natural-language negation is enforced. A soft embedding preference never replaces an explicitly confirmed structured constraint.

There are only four unsupported requests and five negative-intent requests in the evaluation split. Publish raw counts with percentages. This is too small and too subjective to claim a population accuracy, statistical superiority or competitor advantage. If a method has no abstention capability, report that limitation and its actual unsupported-request failures.

## Authoritative constraints and group behavior

Run structured constraint scenarios separately through the actual server matcher with temporary fixtures. The JSON descriptions are review requirements, **not executed evidence**. An embedding ranker must receive only the authoritative feasible set. Measure `returned infeasible candidates / all returned candidates`; if no candidates are returned report the count and a null rate rather than claiming a perfect ratio. Also report scenario pass counts. Exact cents, every confirmed member's limit, per-member timezone, date/time windows, capacity and adjacent seats remain deterministic hard gates. No amount of similarity can override an empty feasible set.

For group aggregation let `s_i(o)` be one member's raw cosine similarity for an eligible offer. Let `ideal_i = max_o s_i(o)` over the **same eligible set**. Opportunity regret is `r_i(o) = ideal_i - s_i(o)`. The proposed method sorts each offer's regret vector descending, then ranks those vectors lexicographically ascending; tie-break by higher mean similarity, schedule and ID. This is lexicographic minimization of worst opportunity loss, not a learned measure of happiness or a new foundation model.

The artificial `fairnessScenarios` matrices have explicit expected winners for lexicographic regret, with mean and leximin comparators where useful. They do not come from a real user or model and cannot establish semantic accuracy. Permuting member order must preserve the selected offer for unchanged utilities. Record these additional per-group diagnostics:

- Minimum absolute member similarity at the selected offer, called `minimumSimilarity`, not satisfaction percentage.
- Maximum member regret and descending regret vector at the selected offer.
- Mean similarity and the selected offer ID under each comparator.
- Whether a candidate is dominated by another candidate for every member.

Regret minimization and maximum minimum utility are different objectives. In `second-worst-member`, lexicographic regret selects `uneven`, whereas leximin selects `balanced`. Publish that tradeoff instead of claiming that regret always maximizes the least satisfied member. Cosines across people are not calibrated welfare measurements, and this tiny catalog cannot validate interpersonal utility comparisons.

## Latency and evidence provenance

Record OS, CPU, runtime/model versions, execution provider, thread count, dtype, pinned revisions, artifact hashes/bytes, document format and fixture SHA. Use a monotonic clock. Report at least:

1. **Cold acquisition:** model/runtime download duration and bytes, with cache state explicitly identified. Do not combine pre-cached model loading with a first-download claim.
2. **Initialization:** tokenizer/session creation and first inference separately from network acquisition.
3. **Corpus embedding:** one-time five-document embedding duration, input lengths and batch size.
4. **Warm uncached query:** initialized session plus cached catalog vectors, new query text per measurement. This includes query tokenization, actual inference, similarity/aggregation and response assembly. Report sample count, p50, p95 and maximum.
5. **Exact-query cache hit:** a separate measurement, labeled cache hit, never presented as model inference latency.
6. **Full browser interaction:** submit-to-render latency on the demo browser, including worker messaging and rendering, when actually observed. Native inference timing does not substitute for this result.

For percentiles state the method; the implemented choice is linear R-7 interpolation at `(n-1)*p` over sorted observations. Give each model the same query order and execution settings. Run one complete untimed warm-up, then several passes, preserving per-query observations rather than only averages. Repeated exact queries must bypass the production query-vector cache for the uncached-inference measurement; do not silently append tokens that change the task. Separate process-level variance from within-process repeats. Do not set a pass threshold retrospectively after observing results. The user has not specified a device class or latency budget beyond a web-based demo, so measured performance is a result rather than a promised service-level target.

Generated reports should be local artifacts outside tracked fixture files and must contain only these synthetic cases. A truthful report distinguishes executed cases, unsupported cases, failed downloads, mocks, native inference and browser observations. The proposed algorithm optimizes useful group decisions and explicit preferences; these metrics do not measure compulsive use, emotional dependence or time spent.

## Research basis

- [Sentence Transformers semantic-search documentation](https://sbert.net/examples/sentence_transformer/applications/semantic-search/README.html) describes embedding-and-similarity retrieval and the importance of query/document task choice.
- [Sentence Transformers InformationRetrievalEvaluator](https://www.sbert.net/docs/package_reference/sentence_transformer/evaluation.html) documents nDCG, MRR and accuracy evaluation. The exact graded-gain and relevance-threshold conventions above are specified here for reproducibility.
- [Järvelin and Kekäläinen, Cumulated Gain-based Evaluation of IR Techniques (2002)](https://doi.org/10.1145/582415.582418) provides the graded-relevance evaluation basis.
- [ONNX Runtime quantization documentation](https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html) states that quantization may reduce accuracy and that performance depends on model/hardware; a smaller model is not automatically faster.
- [ONNX Runtime performance guidance](https://onnxruntime.ai/docs/performance/tune-performance/) treats latency, throughput, memory and application size as distinct measurements.

These sources motivate the protocol; they do not validate this implementation or establish novelty. The application contribution must be described as the constrained integration and its measured behavior, with prior-art comparisons and limitations intact.

## Executed candidate

See [RESULTS.md](RESULTS.md) and results/cpu-comparison.json. The user selected worst modeled compromise as the application default after research, with average and neutral comparison retained. Real-model comparison/selection is diagnostic; neither synthetic fixtures nor the observed 16/16 raw retrieval establishes human group quality. The deployed guard declines 5 of 16 answerable cases and unrelated requests are not reliably rejected. The full authenticated route is measured separately with temporarySQLite; no network/browser/concurrent-load claim follows.

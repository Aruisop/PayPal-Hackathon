"""Reproducible native-CPU evaluation on frozen synthetic catalog fixtures.

This never loads application configuration, opens its database or calls PayPal.
Model assets must be prepared explicitly. No download occurs in this runner.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import re
import subprocess
import time

from evaluation.metrics import quantile, ranking_metrics
from recommendations import EXCLUSION, normalized_mean, regret_order
from model_assets import DEFAULT_ROOT
from semantic import LocalEncoder

ROOT = Path(__file__).resolve().parent
STOP_WORDS = set('a an the i we our my would like want something for with and or to of in at is it'.split())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def keyword(query, offers):
    """Same token/substring policy as browser search, on server-format documents.

    This is deliberately not labeled identical to the browser document format.
    """
    words = set(re.findall('[a-z0-9]+', query.lower())) - STOP_WORDS
    scored = [(sum(word in LocalEncoder.describe(offer).lower() for word in words), offer['id']) for offer in offers]
    return [offer_id for score, offer_id in sorted(scored, key=lambda item: (-item[0], item[1])) if score > 0]


def cosine(vector, documents):
    return [max(-1, min(1, math.fsum(x * y for x, y in zip(vector, document)))) for document in documents]


def aggregate(rows, split):
    chosen = [row for row in rows if row['split'] == split]
    answerable = [row for row in chosen if row['expectedAnswer']]
    unsupported = [row for row in chosen if not row['expectedAnswer']]
    negative = [row for row in chosen if 'negation' in row['tags']]
    values = {}
    for key in ('ndcg@3', 'mrr@3', 'top1Relevant', 'recall@3'):
        numbers = [row['metrics'][key] for row in answerable if row['metrics'][key] is not None]
        values[key] = {'value': math.fsum(numbers) / len(numbers) if numbers else None, 'n': len(numbers)}
    return dict(metrics=values, answerableCount=len(answerable),
                answerCoverage=sum(bool(row['ranked']) for row in answerable),
                unsupportedCount=len(unsupported), unsupportedAbstained=sum(not row['ranked'] for row in unsupported),
                negationCount=len(negative), negationViolationAt1=sum(bool(row['ranked']) and row['ranked'][0] in row['excluded'] for row in negative))


def timed_summary(samples):
    return dict(n=len(samples), p50Ms=quantile(samples, .5), p95Ms=quantile(samples, .95),
                maxMs=max(samples) if samples else None, quantile='linear R-7', queryVectorCache=False)


def query_result(case, ranked, elapsed, scores=None):
    return dict(id=case['id'], split=case['split'], tags=case['tags'], query=case['query'],
                expectedAnswer=case['expectedAnswer'], excluded=case.get('excluded', []), ranked=ranked,
                scores=scores, metrics=ranking_metrics(ranked, case['relevance']), elapsedMs=elapsed)


def group_results(encoder, fixtures, catalog):
    results = []
    by_id = {offer['id']: offer for offer in catalog}
    for group in fixtures['groups']:
        offers = [by_id[offer_id] for offer_id in group['candidateIDs']]
        documents = encoder.catalog(offers)
        tastes = [list(dict.fromkeys(tag.strip().casefold() for tag in member['tastes'] if tag.strip())) for member in group['members']]
        tags = list(dict.fromkeys(tag for member_tags in tastes for tag in member_tags))
        mapping = dict(zip(tags, encoder.encode(tags)))
        matrix = [cosine(normalized_mean([mapping[tag] for tag in member_tags]), documents)
                  for member_tags in tastes if member_tags]
        ids = [offer['id'] for offer in offers]
        orderings = {
            'semantic_regret': regret_order(matrix, ids),
            'mean_cosine': sorted(ids, key=lambda offer_id: (-math.fsum(row[ids.index(offer_id)] for row in matrix) / len(matrix), ids.index(offer_id))),
            'leximin_cosine': sorted(ids, key=lambda offer_id: tuple(-value for value in sorted(row[ids.index(offer_id)] for row in matrix)) + (ids.index(offer_id),)),
        }
        choices = {}
        for method, ranking in orderings.items():
            selected = ranking[0]
            grades = [member['relevance'].get(selected, 0) for member in group['members']]
            regrets = [max(member['relevance'].get(offer_id, 0) for offer_id in ids) - grade
                       for member, grade in zip(group['members'], grades)]
            selected_index = ids.index(selected)
            model_values = [row[selected_index] for row in matrix]
            model_regrets = [max(row) - row[selected_index] for row in matrix]
            choices[method] = dict(selected=selected, minimumLabeledGrade=min(grades),
                                   maximumLabeledRegret=max(regrets), meanLabeledGrade=math.fsum(grades) / len(grades),
                                   perMemberLabeledGrades=grades, perMemberLabeledRegrets=regrets,
                                   minimumSimilarity=min(model_values), maximumModeledRegret=max(model_regrets),
                                   meanSimilarity=math.fsum(model_values) / len(model_values))
        results.append(dict(id=group['id'], choices=choices))
    return results


def model_results(profile, data, groups, repeats, instruction=False):
    encoder = LocalEncoder(profile, query_instruction=instruction)
    if not encoder.status()['available']:
        raise RuntimeError(f'Prepare the {profile} model and optional CPU dependencies first.')
    # Separate session initialization/first forward pass from corpus indexing.
    started = time.perf_counter()
    encoder.encode(['An ordinary example sentence.'])
    first = (time.perf_counter() - started) * 1000
    load = encoder.timings.get('loadMs')
    started = time.perf_counter()
    documents = encoder.catalog(data['catalog'])
    index_ms = (time.perf_counter() - started) * 1000
    ids = [offer['id'] for offer in data['catalog']]
    for case in data['queries']:
        encoder.encode([case['query']])
    rows, latencies, observations = [], [], []
    for repeat in range(repeats):
        for case in data['queries']:
            started = time.perf_counter()
            documents = encoder.catalog(data['catalog'])
            scores = cosine(encoder.encode([case['query']])[0], documents)
            ranked = [ids[i] for i in sorted(range(len(ids)), key=lambda i: (-scores[i], ids[i]))]
            elapsed = (time.perf_counter() - started) * 1000
            latencies.append(elapsed)
            observations.append(dict(passIndex=repeat, queryID=case['id'], elapsedMs=elapsed))
            if repeat == 0:
                rows.append(query_result(case, ranked, elapsed, dict(zip(ids, scores))))
    # Report the actual conservative exclusion guard independently; it declines
    # some answerable requests, and has no general OOD detection capability.
    guarded = [{**row, 'ranked': [], 'metrics': ranking_metrics([], case['relevance'])}
               if EXCLUSION.search(case['query']) else row for row, case in zip(rows, data['queries'])]
    manifest_path = DEFAULT_ROOT / profile / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    return dict(model=encoder.status(), firstForwardIncludingLoadMs=first, loadMs=load,
                assetManifestSHA256=digest(manifest_path), assets=manifest['files'],
                catalogIndexMs=index_ms, latency=timed_summary(latencies),
                warmup='One ordinary first forward pass, then one complete untimed query pass. Models run sequentially in the same Python process.',
                latencyObservations=observations,
                evaluation=aggregate(rows, 'evaluation'), development=aggregate(rows, 'development'),
                exclusionGuardEvaluation=aggregate(guarded, 'evaluation'),
                rawQueries=rows, groups=group_results(encoder, groups, data['catalog']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', choices=['minilm', 'bge', 'all'], default='all')
    parser.add_argument('--repeats', type=int, default=5)
    parser.add_argument('--http', action='store_true', help='Also benchmark the deployed BGE group route against isolated temporary SQLite.')
    parser.add_argument('--output', type=Path, default=ROOT / 'review-artifacts' / 'recommendation-benchmark.json')
    args = parser.parse_args()
    if not 1 <= args.repeats <= 20:
        parser.error('Use 1 to 20 repeated inference passes.')
    fixture = ROOT / 'evaluation' / 'recommendation_cases.json'
    group_fixture = ROOT / 'evaluation' / 'group_cases.json'
    data = json.loads(fixture.read_text(encoding='utf-8'))
    groups = json.loads(group_fixture.read_text(encoding='utf-8'))
    source_files = ['recommendations.py', 'semantic.py', 'model_assets.py', 'benchmark_recommendations.py',
                    'evaluation/metrics.py', 'evaluation/http_benchmark.py', 'server.py', 'planning.py',
                    'ai_planner.py', 'storage.py', 'groups.py']
    report = dict(format=1, timestampUTC=datetime.now(timezone.utc).isoformat(),
        provenance='Actual CPU ONNX inference; synthetic assistant-authored labels, not human reviewed. No browser or real-user evidence.',
        environment=dict(python=platform.python_version(), os=platform.platform(), cpu=platform.processor(), logicalCPUs=os.cpu_count(),
                         provider='CPUExecutionProvider', intraOpThreads=1, interOpThreads=1,
                         packages={name: importlib.metadata.version(name) for name in ['numpy', 'onnxruntime', 'tokenizers']}),
        fixtures=dict(queriesSHA256=digest(fixture), groupsSHA256=digest(group_fixture)),
        source=dict(commit=subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip(),
                    filesSHA256={name: digest(ROOT / name) for name in source_files}),
        scope='Native inference/ranking timings exclude HTTP, database checks, browser rendering and asset downloads. Query vectors are never cached. No numeric latency SLO was supplied.',
        results={})
    keyword_rows, timings, observations = [], [], []
    for repeat in range(args.repeats):
        for case in data['queries']:
            started = time.perf_counter()
            ranked = keyword(case['query'], data['catalog'])
            elapsed = (time.perf_counter() - started) * 1000
            timings.append(elapsed)
            observations.append(dict(passIndex=repeat, queryID=case['id'], elapsedMs=elapsed))
            if repeat == 0:
                keyword_rows.append(query_result(case, ranked, elapsed))
    report['results']['keyword_server_documents'] = dict(evaluation=aggregate(keyword_rows, 'evaluation'),
        development=aggregate(keyword_rows, 'development'), latency=timed_summary(timings),
        latencyObservations=observations, rawQueries=keyword_rows)
    for model in ['minilm', 'bge'] if args.model == 'all' else [args.model]:
        for label, instruction in [(model, False)] + ([('bge_with_instruction', True)] if model == 'bge' else []):
            try:
                report['results'][label] = model_results(model, data, groups, args.repeats, instruction=instruction)
            except Exception as error:
                report['results'][label] = dict(error=type(error).__name__, executed=False)
    if args.http:
        from evaluation.http_benchmark import run_http_benchmark
        try:
            report['http'] = run_http_benchmark(LocalEncoder(model='bge', query_instruction=True), groups, args.repeats)
        except Exception as error:
            report['http'] = dict(error=type(error).__name__, executed=False)
    for name, result in report['results'].items():
        if 'error' in result:
            print(name, 'failed:', result['error'], flush=True)
            continue
        metrics = result['evaluation']['metrics']
        print(name, 'nDCG@3', round(metrics['ndcg@3']['value'], 4), 'Top1', metrics['top1Relevant'],
              'p50/p95 ms', round(result['latency']['p50Ms'], 3), round(result['latency']['p95Ms'], 3), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print('Wrote synthetic evaluation report:', args.output)


if __name__ == '__main__':
    main()

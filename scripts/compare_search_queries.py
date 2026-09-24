"""Compare two query builders against identical queries on the current index."""

import argparse
import asyncio
import fnmatch
import importlib.util
import json
import logging
import math
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.eval_search_intents import CASES, target_name
from src.core.elasticsearch import es_client
from src.search.search_service import SearchService


def load_builder(path):
    spec = importlib.util.spec_from_file_location('comparison_builder', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.QueryBuilder()


def percentile95(values):
    return sorted(values)[math.ceil(len(values) * .95) - 1]


async def main(args):
    logging.disable(logging.CRITICAL)
    if not await es_client.connect():
        raise RuntimeError('Elasticsearch unavailable')
    try:
        cases = json.loads(CASES.read_text(encoding='utf-8'))
        cases += json.loads(CASES.with_name('search_intents_challenge.json').read_text(encoding='utf-8'))
        services = {'before': SearchService(es_client), 'after': SearchService(es_client)}
        services['before'].query_builder = load_builder(args.baseline)
        output = {name: [{'query': c['query'], 'group': c['group'], 'expected': c['expected'],
                          'ms': []} for c in cases] for name in services}
        for repeat in range(args.repeats + 1):
            for number, case in enumerate(cases):
                names = list(services) if (repeat + number) % 2 else list(reversed(services))
                for name in names:
                    start = time.perf_counter()
                    response = await services[name].find_help_filtered(case['query'], [], limit=10)
                    elapsed = (time.perf_counter() - start) * 1000
                    if response.get('search_failed'):
                        raise RuntimeError(response)
                    found = [target_name(doc) for doc in response['results']]
                    rank = next((i for i, actual in enumerate(found, 1)
                                 if any(fnmatch.fnmatchcase(actual, expected)
                                        for expected in case['expected'])), None)
                    item = output[name][number]
                    if 'rank' in item and item['rank'] != rank:
                        raise RuntimeError(f'Unstable rank: {name} {case["query"]}')
                    item.update(rank=rank, top=found[:3])
                    if repeat:
                        item['ms'].append(round(elapsed, 3))
        summary = {}
        for name, items in output.items():
            summary[name] = {}
            for group in ('intent', 'control', 'challenge', 'all'):
                rows = [c for c in items if group == 'all' or c['group'] == group]
                times = [ms for c in rows for ms in c['ms']]
                summary[name][group] = {
                    'total': len(rows), 'top1': sum(c['rank'] == 1 for c in rows),
                    'top3': sum(c['rank'] is not None and c['rank'] <= 3 for c in rows),
                    'median_ms': round(statistics.median(times), 3),
                    'p95_ms': round(percentile95(times), 3)}
        print(json.dumps({'summary': summary, 'cases': output}, ensure_ascii=False, indent=2))
    finally:
        await es_client.disconnect()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True)
    parser.add_argument('--repeats', type=int, choices=range(1, 11), default=5)
    asyncio.run(main(parser.parse_args()))

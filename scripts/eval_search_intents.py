"""Compare fixed natural-language queries and exact-name controls on a live index."""

import asyncio
import fnmatch
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.elasticsearch import es_client
from src.search.search_service import SearchService

CASES = Path(__file__).resolve().parent.parent / 'tests/fixtures/search_intents.json'


def target_name(doc):
    name = doc.get('name_ru') or doc['name'].split(' (')[0]
    owner = doc.get('object_ru') or doc.get('object')
    if doc['type'].startswith('global_') or doc['type'] in ('article', 'object'):
        return name
    return f'{owner}.{name}' if owner else name


async def main():
    logging.disable(logging.CRITICAL)
    if not await es_client.connect():
        raise RuntimeError('Elasticsearch unavailable')
    try:
        service = SearchService(es_client)
        results = []
        for case in json.loads(CASES.read_text(encoding='utf-8')):
            start = time.perf_counter()
            result = await service.find_help_filtered(case['query'], [], limit=10)
            if result.get('search_failed'):
                raise RuntimeError(result)
            names = [target_name(doc) for doc in result['results']]
            rank = next((i for i, name in enumerate(names, 1)
                         if any(fnmatch.fnmatchcase(name, target)
                                for target in case['expected'])), None)
            results.append({**case, 'rank': rank, 'top': names,
                            'ms': round((time.perf_counter() - start) * 1000, 2)})
        summary = {group: {'total': sum(r['group'] == group for r in results),
                          'top1': sum(r['group'] == group and r['rank'] == 1 for r in results),
                          'top3': sum(r['group'] == group and r['rank'] is not None
                                      and r['rank'] <= 3 for r in results)}
                   for group in ('intent', 'control')}
        print(json.dumps({'summary': summary, 'cases': results}, ensure_ascii=False, indent=2))
    finally:
        await es_client.disconnect()


if __name__ == '__main__':
    asyncio.run(main())

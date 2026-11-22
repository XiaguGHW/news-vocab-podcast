"""Synchronize only explicitly listed words from deployed podcast episodes.

Publication adds review candidates, never invented practice or mastery events.
"""
import argparse
import copy
import hashlib
import json
import os
import re
import subprocess
import tempfile
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

VOCAB_PATH = 'learning/vocabulary.json'
LEDGER_PATH = 'learning/podcast_sync.json'


def norm(value):
    return ' '.join(unicodedata.normalize('NFKC', value).strip().lower().replace('’', "'").split())


def fingerprint(words):
    return hashlib.sha256(json.dumps(words, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def published_sources(root, feed):
    """Read the exact feed and source snapshot that was deployed, before fetching newer learning data."""
    ids = []
    for item in ElementTree.parse(feed).findall('./channel/item'):
        guid = item.findtext('guid', '')
        if not guid.startswith('news-vocab-'):
            raise ValueError(f'Unexpected podcast GUID: {guid}')
        ids.append(guid.removeprefix('news-vocab-'))
    sources = []
    for slug in ids:
        if not re.fullmatch(r'[A-Za-z0-9_-]+', slug):
            raise ValueError('Unsafe podcast id')
        episode, story = root / 'episodes' / f'{slug}.json', root / 'stories' / f'{slug}.json'
        if episode.exists():
            source = json.loads(episode.read_text(encoding='utf-8'))
        elif story.exists():
            source = json.loads(story.read_text(encoding='utf-8'))
            if source.get('publish') is not True:
                raise ValueError(f'Story in feed is not approved: {slug}')
        else:
            raise ValueError(f'Published source missing: {slug}')
        if not isinstance(source.get('words'), list):
            raise ValueError(f'{slug}: explicit words list required, including stories')
        sources.append({'id':slug, 'words':source['words']})
    return sources


def validate_record(record):
    ids, events = set(), set()
    for word in record['words']:
        if word['id'] in ids:
            raise ValueError(f'duplicate word id: {word["id"]}')
        ids.add(word['id'])
        if word['status'] not in ('reviewing', 'introduced_unassessed'):
            raise ValueError('invalid learning status')
        for event in word.get('history', []):
            if event['event_id'] in events:
                raise ValueError('duplicate practice event')
            events.add(event['event_id'])


def merge(record, ledger, sources, today):
    record, ledger = copy.deepcopy(record), copy.deepcopy(ledger)
    validate_record(record)
    episodes = ledger.setdefault('episodes', {})
    aliases = {}
    for w in record['words']:
        for alias in [w['id'], w['en'], *w.get('forms', [])]:
            aliases[norm(alias)] = w
    excluded = {norm(w['en']) for w in record.get('excluded_words', [])}
    stats = {'added':0, 'linked':0, 'excluded':0, 'processed':0}
    old_record = copy.deepcopy(record)
    for source in sources:
        slug, words = source['id'], source['words']
        digest = fingerprint(words)
        if episodes.get(slug, {}).get('words_hash') == digest:
            continue
        for candidate in words:
            if not isinstance(candidate, dict) or not all(isinstance(candidate.get(k), str) and candidate[k].strip() for k in ('en', 'zh')):
                raise ValueError(f'{slug}: words require nonempty en and zh')
            lemma = candidate.get('lemma', candidate['en']).strip()
            if not lemma:
                raise ValueError(f'{slug}: empty lemma')
            if norm(lemma) in excluded or norm(candidate['en']) in excluded:
                stats['excluded'] += 1
                continue
            explicit_id = candidate.get('learning_id')
            existing = aliases.get(norm(explicit_id)) if explicit_id else (aliases.get(norm(lemma)) or aliases.get(norm(candidate['en'])))
            if not isinstance(candidate.get('forms', []), list):
                raise ValueError('forms must be a list')
            forms = list(candidate.get('forms', []))
            if any(not isinstance(form, str) or not form.strip() for form in forms):
                raise ValueError('forms must be a list of nonempty strings')
            if norm(lemma) != norm(candidate['en']):
                forms.append(candidate['en'])
            if existing is None:
                word_id = candidate.get('learning_id') or re.sub(r'[^a-z0-9]+', '-', norm(lemma)).strip('-')
                if not word_id or any(w['id'] == word_id for w in record['words']):
                    raise ValueError(f'{slug}: ambiguous word id; set learning_id explicitly')
                existing = {'id':word_id, 'en':lemma, 'forms':[], 'zh':candidate['zh'],
                            'de':candidate.get('de', ''), 'added_on':today.isoformat(),
                            'learning_source':'podcast_auto_sync', 'episode_ids':[],
                            'priority':'normal', 'status':'introduced_unassessed',
                            'last_practiced_on':None, 'next_review_on':(today + timedelta(days=1)).isoformat(),
                            'notes':['由已发布播客的明确词表自动加入复习池；未确认收听、练习或掌握。'], 'history':[]}
                if candidate.get('ipa'):
                    existing['ipa'] = candidate['ipa']
                record['words'].append(existing)
                stats['added'] += 1
            for form in forms:
                if norm(form) != norm(existing['en']) and form not in existing['forms']:
                    existing['forms'].append(form)
            if slug not in existing['episode_ids']:
                existing['episode_ids'].append(slug)
                stats['linked'] += 1
            for alias in [existing['id'], existing['en'], *existing['forms']]:
                aliases[norm(alias)] = existing
        episodes[slug] = {'words_hash':digest, 'synced_on':today.isoformat(), 'word_count':len(words)}
        stats['processed'] += 1
    if record != old_record:
        record['updated_on'] = today.isoformat()
    validate_record(record)
    return record, ledger, stats


def git(root, *args, stdin=None, env=None):
    result = subprocess.run(['git', *args], cwd=root, input=stdin, capture_output=True, text=True, env=env)
    if result.returncode:
        raise RuntimeError(result.stderr)
    return result.stdout.strip()


def encoded(data):
    return json.dumps(data, ensure_ascii=False, indent=2) + '\n'


def push_updates(root, sources, today):
    """Retry from the latest remote learning record; never overwrite answers or force-push."""
    for attempt in range(4):
        git(root, 'fetch', 'origin', 'main')
        parent = git(root, 'rev-parse', 'refs/remotes/origin/main')
        original = json.loads(git(root, 'show', f'{parent}:{VOCAB_PATH}'))
        old_ledger = json.loads(git(root, 'show', f'{parent}:{LEDGER_PATH}'))
        record, ledger, stats = merge(original, old_ledger, sources, today)
        if record == original and ledger == old_ledger:
            return stats, parent
        # A private index keeps the checkout and any user's working changes untouched.
        with tempfile.TemporaryDirectory(prefix='vocabulary-sync-') as folder:
            env = dict(os.environ, GIT_INDEX_FILE=str(Path(folder) / 'index'))
            git(root, 'read-tree', parent, env=env)
            for path, data in ((VOCAB_PATH, record), (LEDGER_PATH, ledger)):
                blob = git(root, 'hash-object', '-w', '--stdin', stdin=encoded(data))
                git(root, 'update-index', '--add', '--cacheinfo', f'100644,{blob},{path}', env=env)
            tree = git(root, 'write-tree', env=env)
            sha = git(root, 'commit-tree', tree, '-p', parent, '-m', 'Sync published podcast vocabulary [skip ci]')
        try:
            git(root, 'push', 'origin', f'{sha}:refs/heads/main')
            # The successful fast-forward push confirms this exact merged record is stored.
            return stats, sha
        except RuntimeError:
            if attempt == 3:
                raise
    raise RuntimeError('Vocabulary sync did not finish')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--feed', type=Path, default=Path('site/feed.xml'))
    parser.add_argument('--commit', action='store_true', help='Commit merged learning files to latest origin/main')
    parser.add_argument('--check', action='store_true', help='Fail if this published snapshot still needs syncing')
    parser.add_argument('--dry-run', action='store_true', help='Validate and show planned imports without writing')
    args = parser.parse_args()
    if sum((args.commit, args.check, args.dry_run)) > 1:
        parser.error('--commit, --check, and --dry-run are mutually exclusive')
    root = Path.cwd()
    sources = published_sources(root, args.feed)
    today = datetime.now(ZoneInfo('Europe/Berlin')).date()
    if args.commit:
        stats, sha = push_updates(root, sources, today)
        print(json.dumps(dict(stats, commit=sha), ensure_ascii=False))
        return
    original = json.loads((root / VOCAB_PATH).read_text(encoding='utf-8'))
    old_ledger = json.loads((root / LEDGER_PATH).read_text(encoding='utf-8'))
    record, ledger, stats = merge(original, old_ledger, sources, today)
    if args.check:
        if record != original or ledger != old_ledger:
            raise SystemExit('Published vocabulary has not been fully synchronized')
    elif not args.dry_run:
        (root / VOCAB_PATH).write_text(encoded(record), encoding='utf-8')
        (root / LEDGER_PATH).write_text(encoded(ledger), encoding='utf-8')
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == '__main__':
    main()

import copy
import json
import subprocess
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import sync_podcast_vocabulary as sync


class PodcastSyncTests(unittest.TestCase):
    def setUp(self):
        self.today = date(2026, 11, 22)
        self.record = {'words': [{'id': 'retrieve', 'en': 'retrieve', 'forms': ['retrieved'],
            'zh': '检索', 'episode_ids': ['old'], 'priority': 'high', 'status': 'reviewing',
            'last_practiced_on': '2026-11-21', 'next_review_on': '2026-11-22',
            'history': [{'event_id': 'answer-1', 'result': 'hinted_correct'}]}],
            'excluded_words': [{'en': 'robust'}], 'updated_on': '2026-11-21'}
        self.sources = [{'id': 'new', 'words': [
            {'en': 'retrieved', 'lemma': 'retrieve', 'zh': '检索'},
            {'en': 'nuanced', 'zh': '有细微差别的', 'de': 'differenziert'},
            {'en': 'NUANCED', 'zh': '有细微差别的'},
            {'en': 'robust', 'zh': '稳健的'}]}]

    def test_merge_preserves_practice_and_is_idempotent(self):
        original = copy.deepcopy(self.record)
        record, ledger, stats = sync.merge(self.record, {}, self.sources, self.today)
        self.assertEqual(stats['added'], 1)
        self.assertEqual(stats['excluded'], 1)
        self.assertEqual(len(record['words']), 2)
        old = dict(record['words'][0], episode_ids=['old'])
        self.assertEqual(old, original['words'][0])
        new = record['words'][1]
        self.assertEqual(new['status'], 'introduced_unassessed')
        self.assertEqual(new['history'], [])
        self.assertEqual(new['next_review_on'], '2026-11-23')
        self.assertEqual(new['episode_ids'], ['new'])
        again, ledger2, stats2 = sync.merge(record, ledger, self.sources, date(2026, 11, 24))
        self.assertEqual(again, record)
        self.assertEqual(ledger2, ledger)
        self.assertEqual(stats2['processed'], 0)
        self.assertEqual(self.record, original)

    def test_feed_filters_sources_and_requires_explicit_story_words(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'stories').mkdir()
            feed = root / 'feed.xml'
            feed.write_text('<rss><channel><item><guid>news-vocab-published</guid></item></channel></rss>')
            path = root / 'stories/published.json'
            path.write_text(json.dumps({'publish': True}))
            with self.assertRaisesRegex(ValueError, 'words list'):
                sync.published_sources(root, feed)
            path.write_text(json.dumps({'publish': True, 'words': []}))
            (root / 'stories/preview.json').write_text('{"publish":false}')
            self.assertEqual(sync.published_sources(root, feed), [{'id': 'published', 'words': []}])

    def test_rejects_missing_translation(self):
        with self.assertRaises(ValueError):
            sync.merge(self.record, {}, [{'id': 'new', 'words': [{'en': 'word'}]}], self.today)

    def test_push_retries_concurrent_answer_without_touching_checkout(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            remote, work, other = root/'remote.git', root/'work', root/'other'
            subprocess.run(['git', 'init', '--bare', str(remote)], check=True, capture_output=True)
            subprocess.run(['git', 'clone', str(remote), str(work)], check=True, capture_output=True)
            for repo in (work,):
                sync.git(repo, 'config', 'user.name', 'test')
                sync.git(repo, 'config', 'user.email', 'test@example.invalid')
            (work/'learning').mkdir()
            (work/sync.VOCAB_PATH).write_text(sync.encoded(self.record))
            (work/sync.LEDGER_PATH).write_text('{}')
            sync.git(work, 'add', '.')
            sync.git(work, 'commit', '-m', 'initial')
            sync.git(work, 'branch', '-M', 'main')
            sync.git(work, 'push', '-u', 'origin', 'main')
            subprocess.run(['git', 'clone', '-b', 'main', str(remote), str(other)], check=True, capture_output=True)
            sync.git(other, 'config', 'user.name', 'test')
            sync.git(other, 'config', 'user.email', 'test@example.invalid')
            original_git = sync.git
            raced = False
            def racing_git(repo, *args, **kwargs):
                nonlocal raced
                if args[0] == 'push' and not raced:
                    raced = True
                    answer = copy.deepcopy(self.record)
                    answer['words'][0]['history'].append({'event_id': 'concurrent-answer', 'result': 'independent_correct'})
                    (other/sync.VOCAB_PATH).write_text(sync.encoded(answer))
                    original_git(other, 'add', '.')
                    original_git(other, 'commit', '-m', 'answer')
                    original_git(other, 'push')
                return original_git(repo, *args, **kwargs)
            checkout_head = sync.git(work, 'rev-parse', 'HEAD')
            with patch.object(sync, 'git', side_effect=racing_git):
                stats, sha = sync.push_updates(work, self.sources, self.today)
            saved = json.loads(sync.git(work, 'show', f'{sha}:{sync.VOCAB_PATH}'))
            self.assertEqual(saved['words'][0]['history'][-1]['event_id'], 'concurrent-answer')
            self.assertEqual(stats['added'], 1)
            self.assertEqual(sync.git(work, 'rev-parse', 'HEAD'), checkout_head)
            self.assertEqual(sync.git(work, 'status', '--porcelain'), '')

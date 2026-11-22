import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import build_review as review
import review_podcast
import sync_podcast_vocabulary as sync


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.sources=[json.loads(Path(f'reviews/2026-11-23-review{i}.json').read_text()) for i in (1,2)]

    def test_all_49_words_once_with_two_parts(self):
        actual=[w['learning_id'] for d in self.sources for w in d['words']]
        self.assertEqual([len(d['words']) for d in self.sources],[25,24])
        # This is a dated 49-word snapshot; future vocabulary additions must not
        # require rewriting historical review episodes.
        self.assertEqual(len(actual),49)
        self.assertEqual(len(set(actual)),49)

    def test_question_pause_and_three_examples_one_translation(self):
        for d in self.sources:
            review.validate(d,check_images=False)
            segments=review.plan(d)
            for i,w in enumerate(d['words']):
                rows=[s for s in segments if s['index']==i and s['phase']!='intro']
                self.assertEqual(rows[0]['phase'],'question')
                self.assertEqual(rows[0]['pause'],3)
                self.assertEqual([s['rate'] for s in rows if s.get('rep')],['-20%','-20%','-10%'])
                self.assertEqual([s['t'] for s in rows if s.get('rep')],[w['example']]*3)
                self.assertEqual(sum(s['l']=='zh' and s['t']==w['translation'] for s in rows),1)
                self.assertFalse(any(s['phase']=='answer' for s in rows))

    def test_source_in_feed_requires_publication_authorization(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'reviews').mkdir()
            feed=root/'feed.xml'
            feed.write_text('<rss><channel><item><guid>news-vocab-review</guid></item></channel></rss>')
            source=root/'reviews/review.json'
            source.write_text('{"publish":false,"words":[]}')
            with self.assertRaises(ValueError):sync.published_sources(root,feed)
            source.write_text('{"publish":true,"words":[]}')
            self.assertEqual(sync.published_sources(root,feed),[{'id':'review','words':[]}])

    def test_unapproved_review_does_not_enter_feed(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'preview.json';p.write_text('{"publish":false}')
            self.assertIsNone(review_podcast.review_episode(p))

    def test_question_card_hides_answer_and_image(self):
        d=self.sources[0];s=review.plan(d)[1]
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(review.Image,'open',side_effect=AssertionError('question opened answer image')):
                review.card(d,s,Path(folder)/'question.png',3)

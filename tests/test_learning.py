"""运行 python3 -m unittest discover -s tests。无语音或网络调用。"""
import tempfile
import unittest
from unittest.mock import patch

import build
import check_episode
import video


def episode():
    return {
        'format_version': 2, 'id': '2026-11-21-demo', 'date': '2026-11-21',
        'pub': '2026-11-21T10:00:00+01:00', 'title': '回忆测试',
        'topic': '词汇专题', 'summary': '调取文件。', 'pic': '📚', 'sources': [],
        'words': [{'en': 'retrieve', 'de': 'abrufen', 'zh': '调取',
                   'ipa': '/rɪˈtriːv/', 'pic': '🔍'}],
        'segments': [
            {'l': 'zh', 't': '今天学习调取文件。', 'sec': 'intro'},
            {'l': 'zh', 't': '第一个词。', 'sec': 1},
            {'l': 'en', 't': 'retrieve.'},
            {'l': 'zh', 't': '开始小测。', 'sec': 'quiz'},
            {'l': 'zh', 't': '从数据库里调出文件，怎么说？', 'p': 4, 'sec': 'recall:1'},
            {'l': 'en', 't': 'retrieve.', 'sec': 'answer:1'},
            {'l': 'de', 't': 'abrufen.'},
        ],
    }


class LearningTests(unittest.TestCase):
    def test_new_format_and_legacy(self):
        self.assertEqual(check_episode.validate_learning(episode()), [])
        self.assertEqual(check_episode.validate_learning({'words': []}), [])

    def test_reject_missing_answer_pause_and_coverage(self):
        for mutation in ('answer', 'pause', 'coverage', 'ipa', 'pic'):
            ep = episode()
            if mutation == 'answer':
                ep['segments'][5]['sec'] = 'answer:2'
            elif mutation == 'pause':
                ep['segments'][4]['p'] = 0.4
            elif mutation == 'coverage':
                ep['segments'] = ep['segments'][:4]
            else:
                ep['words'][0].pop(mutation)
            with self.subTest(mutation=mutation):
                self.assertTrue(check_episode.validate_learning(ep))

    def test_nonrepeated_long_sentence_still_needs_translation(self):
        ep = episode()
        ep['segments'].insert(3, {'l': 'en', 't': 'She retrieved the report from storage.', 'repeat': False})
        self.assertTrue(check_episode.validate_learning(ep))

    def test_build_preserves_recall_and_answer_markers(self):
        ep = episode()
        expanded = build.expand_segments(ep['segments'])
        self.assertEqual([s['sec'] for s in expanded if 'sec' in s],
                         ['intro', 1, 'quiz', 'recall:1', 'answer:1'])

    def test_question_frames_never_draw_answers_or_history(self):
        ep = episode()
        ep['segments'] = [ep['segments'][4]]
        meta = {'duration': 7, 'cues': [{'start': 0, 'l': 'zh', 't': ep['segments'][0]['t']}]}
        # Neither the spoken question nor its pause may draw prior answers.
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(video, 'draw_word_card', side_effect=AssertionError('answer leak')), \
             patch.object(video, 'card_quiz', side_effect=AssertionError('answer leak')), \
             patch.object(video, 'card_intro', side_effect=AssertionError('history leak')), \
             patch.object(video, 'subtitles', side_effect=AssertionError('history leak')):
            frames = video.render_frames(ep, meta, tmp)
            self.assertEqual(len(frames), 2)
            self.assertAlmostEqual(sum(d for _, d in frames), 7)

    def test_answer_frame_renders(self):
        ep = episode()
        ep['segments'] = [ep['segments'][5]]
        meta = {'duration': 2, 'cues': [{'start': 0, 'l': 'en', 't': 'retrieve.'}]}
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(len(video.render_frames(ep, meta, tmp)), 1)


if __name__ == '__main__':
    unittest.main()

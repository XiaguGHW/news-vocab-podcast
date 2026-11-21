"""朗读策略、字幕速度及旧稿兼容性回归测试。"""
import glob
import json
import unittest
from pathlib import Path

import build
import check_episode
import video


class ReadingTests(unittest.TestCase):
    def test_example_translates_once_and_preserves_marker(self):
        seg = dict(l='en', t='She compiled a list of useful sources.', zh='她整理了一份有用资料来源清单。',
                   p=.5, sec=1, reading='example')
        out = build.expand_segments([seg])
        self.assertEqual([x['l'] for x in out], ['en', 'en', 'zh'])
        self.assertEqual([x['rate'] for x in out[:2]], ['-20%', '-10%'])
        self.assertEqual([x.get('sec') for x in out], [1, None, None])
        self.assertEqual([x['speed'] for x in out[:2]], ['0.8×', '0.9×'])
        self.assertEqual(out[-1]['p'], .5)

    def test_long_shadow_and_answer_are_single_readings(self):
        for role in ('shadow', 'answer'):
            seg = dict(l='de', t='einen Bericht aus mehreren Quellen zusammenstellen.',
                       zh='用多个来源整理报告。', p=3, sec='answer:1', reading=role)
            out = build.expand_segments([seg])
            self.assertEqual(len(out), 1)
            self.assertEqual(out[0]['p'], 3)
            self.assertEqual(out[0]['sec'], 'answer:1')

    def test_short_example_also_translates(self):
        out = build.expand_segments([dict(l='en', t='Keep the receipt.', zh='保留收据。', reading='example')])
        self.assertEqual(len(out), 3)
        self.assertEqual(out[-1]['l'], 'zh')

    def test_all_existing_episodes_keep_expansion(self):
        # Emulate the previous implementation for every legacy published script.
        def old_expand(segments):
            out = []
            for seg in segments:
                if not build.is_sentence(seg):
                    out.append(seg)
                    continue
                for k, rate in enumerate(build.SENTENCE_RATES):
                    c = dict(l=seg['l'], t=seg['t'], rate=rate, rep=k+1, p=.9, zh=seg.get('zh',''))
                    if k == 0 and 'sec' in seg:
                        c['sec'] = seg['sec']
                    out.append(c)
                if seg.get('zh'):
                    out[-1]['p'] = .6
                    out.append(dict(l='zh', t=seg['zh'], p=seg.get('p', .45), zh_for=True))
                else:
                    out[-1]['p'] = seg.get('p', .45)
            return out
        for path in glob.glob('episodes/*.json'):
            ep = json.loads(Path(path).read_text())
            if ep.get('format_version') == 2:
                continue
            self.assertEqual(build.expand_segments(ep['segments']), old_expand(ep['segments']), path)

    def test_pilot_expansion_renders_and_passes_checks(self):
        ep = json.loads(Path('episodes/2026-11-21-vocab3.json').read_text())
        self.assertEqual(check_episode.validate_learning(ep), [])
        segs = build.expand_segments(ep['segments'])
        ep['segments'] = segs
        meta = dict(duration=len(segs)*6, cues=[dict(start=i*6,l=s['l'],t=s['t'],
                      **{k:s[k] for k in ('rep','speed') if k in s}) for i,s in enumerate(segs)])
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            frames = video.render_frames(ep, meta, tmp)
            self.assertAlmostEqual(sum(d for _,d in frames), meta['duration'])

    def test_invalid_role_and_short_shadow_are_rejected(self):
        from test_learning import episode
        for role, pause in [('unknown',3), ('shadow',.5)]:
            ep=episode()
            ep['segments'][2].update(reading=role,p=pause)
            self.assertTrue(check_episode.validate_learning(ep))


if __name__ == '__main__':
    unittest.main()

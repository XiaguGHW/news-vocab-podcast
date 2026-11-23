import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
import build
import check_episode
import episode_assets as assets
import video
from test_learning import episode


class IllustrationTests(unittest.TestCase):
    def fixture(self,root):
        p=root/'assets/episodes/demo/scene.jpg';p.parent.mkdir(parents=True)
        Image.new('RGB',(400,400),'orange').save(p)
        ep=episode();ep['format_version']=3
        ep['illustrations']=[{'path':'assets/episodes/demo/scene.jpg','prompt':'A file retrieved from a database.'}]
        ep['segments'].insert(3,{'l':'en','t':'She retrieved the report from storage.',
            'zh':'她从存储中调取了报告。','reading':'example','illustration':ep['illustrations'][0]['path']})
        return ep,p

    def test_each_reading_and_translation_retains_same_image(self):
        seg={'l':'de','t':'Sie ruft den Bericht aus dem Archiv ab.','zh':'她从档案中调取报告。',
             'reading':'example','illustration':'assets/episodes/demo/scene.jpg'}
        out=build.expand_segments([seg])
        self.assertEqual([s['illustration'] for s in out],[seg['illustration']]*4)
        self.assertEqual([s['rate'] for s in out[:3]],['-20%','-20%','-10%'])
        self.assertEqual(out[3]['example_text'],seg['t'])
        self.assertEqual(out[3]['example_lang'],'de')

    def test_missing_broken_unsafe_and_undeclared_images_rejected(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(assets,'ROOT',Path(folder)):
            ep,p=self.fixture(Path(folder))
            self.assertEqual(check_episode.validate_learning(ep),[])
            original=copy.deepcopy(ep)
            for value in (None,'../outside.jpg','assets/episodes/demo/missing.jpg'):
                ep=copy.deepcopy(original);ep['segments'][3]['illustration']=value
                self.assertTrue(check_episode.validate_learning(ep))
            ep=copy.deepcopy(original);ep['illustrations']=[]
            self.assertTrue(check_episode.validate_learning(ep))
            p.write_bytes(b'not an image')
            self.assertTrue(check_episode.validate_learning(original))

    def test_image_change_invalidates_only_new_format_fingerprint(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(assets,'ROOT',Path(folder)):
            root=Path(folder);ep,p=self.fixture(root)
            for name in ('video.py','episode_assets.py'):(root/name).write_text('renderer')
            source=root/'episode.json';source.write_text(json.dumps(ep))
            before=assets.source_hash(source,ep)
            Image.new('RGB',(400,400),'blue').save(p)
            self.assertNotEqual(before,assets.source_hash(source,ep))
            ep['format_version']=2
            before=assets.source_hash(source,ep)
            Image.new('RGB',(400,400),'red').save(p)
            self.assertEqual(before,assets.source_hash(source,ep))

    def test_question_never_opens_illustration(self):
        ep=episode();ep['segments']=[dict(ep['segments'][4],illustration='assets/episodes/demo/scene.jpg')]
        meta={'duration':7,'cues':[{'start':0,'l':'zh','t':ep['segments'][0]['t']}]}
        with tempfile.TemporaryDirectory() as folder,patch.object(video,'illustrated_example',side_effect=AssertionError('answer leak')):
            self.assertEqual(len(video.render_frames(ep,meta,folder)),2)

    def test_picture_renderer_used_during_foreign_and_chinese(self):
        seg={'l':'en','t':'She retrieved the report from storage.','zh':'她从存储中调取了报告。',
             'reading':'example','illustration':'assets/episodes/demo/scene.jpg','sec':1}
        ep=episode();ep['segments']=build.expand_segments([seg])
        cues=[dict(start=i*4,l=s['l'],t=s['t']) for i,s in enumerate(ep['segments'])]
        with tempfile.TemporaryDirectory() as folder,patch.object(video,'illustrated_example') as picture:
            frames=video.render_frames(ep,dict(duration=16,cues=cues),folder)
            self.assertEqual(picture.call_count,4)
            self.assertAlmostEqual(sum(d for _,d in frames),16)

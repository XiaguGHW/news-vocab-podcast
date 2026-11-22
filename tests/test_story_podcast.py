import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from xml.etree import ElementTree

import build
from story_podcast import build_published_story, story_episode, STORY_MEDIA_VERSION


class StoryPublicationTests(unittest.TestCase):
    def setUp(self):
        self.story = {'schema_version':1, 'id':'test-story', 'title':'A quiet afternoon',
                      'title_zh':'安静的午后', 'date':'2026-11-22',
                      'pub':'2026-11-22T12:00:00+01:00', 'publish':True,
                      'orientation':'portrait', 'segments':[
                          {'speaker':'Narrator', 'en':'Mia smiled.', 'zh':'米娅笑了。'}]}

    def test_publication_requires_explicit_flag_and_zoned_date(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'story.json'
            for flag in (False, None, 'true'):
                path.write_text(json.dumps(dict(self.story, publish=flag)))
                self.assertIsNone(story_episode(path))
            path.write_text(json.dumps(self.story))
            ep, digest = story_episode(path)
            self.assertEqual(ep['_orientation'], 'portrait')
            self.assertEqual(ep['kind'], 'story')
            self.assertEqual(len(digest), 16)
            path.write_text(json.dumps(dict(self.story, pub='2026-11-22T12:00:00')))
            with self.assertRaises(ValueError):
                story_episode(path)

    def test_story_and_normal_episode_both_remain_in_feeds(self):
        meta = {'duration':42, 'size':100, 'video_size':200,
                'cues':[{'start':0, 'l':'en', 't':'Mia smiled.', 'zh':'米娅笑了。', 'speaker':'Narrator'}]}
        story = dict(self.story, title='安静的午后', kind='story', words=[])
        normal = {'id':'2026-11-21', 'date':'2026-11-21', 'title':'词汇专题', 'words':[]}
        for mode in ('audio', 'video'):
            feed = ElementTree.fromstring(build.feed_xml([(story, meta), (normal, meta)], mode))
            items = feed.findall('./channel/item')
            self.assertEqual(len(items), 2)
            self.assertIn('test-story', items[0].find('enclosure').attrib['url'])
            self.assertIn('2026-11-21', items[1].find('enclosure').attrib['url'])
            self.assertIn('米娅笑了', items[0].findtext('description'))

    def test_unchanged_published_story_is_not_rebuilt_or_uploaded(self):
        with tempfile.TemporaryDirectory() as folder:
            meta = Path(folder) / 'episodes' / 'test-story.json'
            meta.parent.mkdir()
            meta.write_text(json.dumps({'src_hash':'unchanged', 'story_v':STORY_MEDIA_VERSION}))
            upload = Mock()
            self.assertFalse(build_published_story({'id':'test-story'}, 'unchanged', folder, folder, upload))
            upload.assert_not_called()


if __name__ == '__main__':
    unittest.main()

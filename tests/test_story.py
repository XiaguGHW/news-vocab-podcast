import copy
import tempfile
import unittest
from pathlib import Path

import build_story as story


class StoryTests(unittest.TestCase):
    def setUp(self):
        self.data = {'schema_version':1, 'id':'test-story', 'title':'A quiet afternoon',
                     'title_zh':'安静的午后', 'segments':[
                         {'speaker':'Narrator', 'en':'Mia smiled.', 'zh':'米娅笑了。'},
                         {'speaker':'Mia', 'en':'“I can take a break.”', 'zh':'“我可以休息一会儿。”'}]}

    def test_approved_voice_mapping_and_quotes(self):
        voices = story.validate(self.data)
        self.assertEqual(voices['Narrator'], 'en-US-JennyNeural')
        self.assertEqual(voices['Mia'], 'en-US-AvaNeural')
        self.assertEqual(voices['Rosa'], 'en-US-EmmaNeural')
        self.assertEqual(story.display_text(self.data['segments'][1], 'en'), '"I can take a break."')
        self.assertEqual(story.display_text(self.data['segments'][1], 'zh'), '“我可以休息一会儿。”')
        self.assertEqual(story.display_text(self.data['segments'][0], 'en'), 'Mia smiled.')

    def test_invalid_speaker_or_chinese_spoken_text(self):
        for change in ({'speaker':'Unknown'}, {'en':'Mia说 hello.'}):
            data = copy.deepcopy(self.data)
            data['segments'][0].update(change)
            with self.assertRaises(ValueError):
                story.validate(data)
        for speed in (True, float('nan'), 0.1):
            with self.assertRaises(ValueError):
                story.validate(dict(self.data, speed=speed))

    def test_both_layouts_fit_long_sentence(self):
        segment = {'speaker':'Rosa', 'en':"There is a more nuanced way to think about responsibility: doing your share matters, but so does trusting others.",
                   'zh':'可以更细致地理解责任：做好自己的部分很重要，相信别人也很重要。'}
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            for orientation, dimensions in story.SIZES.items():
                dest = Path(folder) / f'{orientation}.png'
                story.render_card(self.data, segment, 0, 1, orientation, dest)
                with Image.open(dest) as image:
                    self.assertEqual(image.size, dimensions)
                    self.assertEqual(image.getpixel((0, 0)), (17, 21, 27))


if __name__ == '__main__':
    unittest.main()

"""Publish explicitly approved English stories through the existing podcast feed."""
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from PIL import Image
from build_story import validate

STORY_MEDIA_VERSION = 1


def story_episode(path):
    path = Path(path)
    story = json.loads(path.read_text(encoding='utf-8'))
    if story.get('publish') is not True:
        return None
    validate(story)
    date.fromisoformat(story['date'])
    pub = datetime.fromisoformat(story['pub'])
    if pub.utcoffset() is None:
        raise ValueError(f'{path}: pub requires a timezone')
    orientation = story.get('podcast_orientation', story.get('orientation', 'portrait'))
    if orientation == 'both':
        orientation = 'portrait'
    if orientation not in ('portrait', 'landscape'):
        raise ValueError(f'{path}: invalid podcast_orientation')
    ep = {key: story[key] for key in ('id', 'date', 'pub')}
    ep.update(kind='story', title=story.get('podcast_title', story['title_zh'] + '｜全文英语多角色故事'),
              summary=story.get('summary', story['title']), words=story.get('words', []),
              sources=[], _story_path=str(path.resolve()), _orientation=orientation)
    digest = hashlib.sha256(path.read_bytes())
    for module in ('build_story.py', 'story_podcast.py'):
        digest.update(Path(__file__).with_name(module).read_bytes())
    return ep, digest.hexdigest()[:16]


def build_published_story(ep, src_hash, docs, dist, release_upload):
    slug = ep['id']
    meta_path = Path(docs) / 'episodes' / f'{slug}.json'
    if meta_path.exists():
        old = json.loads(meta_path.read_text())
        if old.get('src_hash') == src_hash and old.get('story_v') == STORY_MEDIA_VERSION:
            return False
    print('build story', slug, flush=True)
    root = Path(__file__).resolve().parent
    subprocess.run([sys.executable, str(root / 'build_story.py'), ep['_story_path'],
                    '--orientation', ep['_orientation'], '--mp3',
                    '--output-dir', str(Path(dist).resolve() / 'stories')], check=True)
    folder = Path(dist) / 'stories' / slug
    mp3, mp4 = Path(dist) / f'{slug}.mp3', Path(dist) / f'{slug}.mp4'
    shutil.copyfile(folder / f'{slug}.mp3', mp3)
    shutil.copyfile(folder / f'{slug}-{ep["_orientation"]}.mp4', mp4)
    with Image.open(folder / f'{ep["_orientation"]}-preview.png') as im:
        im.convert('RGB').save(meta_path.with_suffix('.jpg'), quality=90)
    timeline = json.loads((folder / 'timeline.json').read_text())['timeline']
    meta = {'story_v':STORY_MEDIA_VERSION, 'src_hash':src_hash, 'duration':round(timeline[-1]['end']),
            'size':mp3.stat().st_size, 'video_size':mp4.stat().st_size,
            'built':datetime.now(timezone.utc).isoformat(),
            'cues':[{'start':round(s['start'], 2), 'l':'en', 't':s['en'], 'zh':s['zh'],
                     'speaker':s['speaker']} for s in timeline]}
    release_upload(ep, [str(mp3), str(mp4)])
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding='utf-8')
    return True

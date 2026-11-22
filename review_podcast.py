"""Publish approved illustrated review sources through the existing feeds."""
import hashlib
import json
import shutil
from pathlib import Path

from PIL import Image
from build_review import validate, build, ROOT


def review_episode(path):
    path=Path(path);data=json.loads(path.read_text())
    if data.get('publish') is not True:return None
    validate(data)
    ep={k:data[k] for k in ('id','date','pub','title','summary','words')}
    ep.update(kind='review',sources=[],_review_path=str(path.resolve()))
    digest=hashlib.sha256(path.read_bytes())
    for name in ('build_review.py','review_podcast.py'):
        digest.update((ROOT/name).read_bytes())
    for w in data['words']:digest.update((ROOT/w['image']).read_bytes())
    return ep,digest.hexdigest()[:16]


def build_published_review(ep,src_hash,docs,dist,release_upload):
    meta_path=Path(docs)/'episodes'/f"{ep['id']}.json"
    if meta_path.exists():
        old=json.loads(meta_path.read_text())
        if old.get('src_hash')==src_hash and old.get('review_v')==1:return False
    data=json.loads(Path(ep['_review_path']).read_text())
    folder=build(data,(Path(dist)/'reviews').resolve(),ROOT/'.cache'/'review-tts')
    files=[]
    for extension in ('mp3','mp4'):
        dest=Path(dist)/f"{ep['id']}.{extension}"
        shutil.copyfile(folder/dest.name,dest);files.append(str(dest))
    timeline=json.loads((folder/'timeline.json').read_text())
    with Image.open(folder/'example-000.png') as im:
        im.resize((540,960)).save(meta_path.with_suffix('.jpg'),quality=88)
    release_upload(ep,files)
    meta={'review_v':1,'src_hash':src_hash,'duration':round(timeline['duration']),
          'size':Path(files[0]).stat().st_size,'video_size':Path(files[1]).stat().st_size,
          'cues':[{'start':round(s['start'],2),'l':s['l'],'t':s['t']} for s in timeline['segments']]}
    meta_path.write_text(json.dumps(meta,ensure_ascii=False,indent=1))
    return True

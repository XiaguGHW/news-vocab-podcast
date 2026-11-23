"""Shared image validation and cache fingerprints for illustrated lessons."""
import hashlib
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent


def image_path(value):
    if not isinstance(value,str) or not value.strip():
        raise ValueError('例句缺少 illustration 配图路径')
    relative=Path(value)
    path=(ROOT/relative).resolve()
    allowed=any(path.is_relative_to((ROOT/'assets'/kind).resolve()) for kind in ('episodes','review'))
    if relative.is_absolute() or not allowed:
        raise ValueError('配图必须位于仓库 assets/episodes 或 assets/review 中')
    return path


def validate_illustrations(ep):
    errors=[]
    declared={}
    manifest=ep.get('illustrations',[])
    if not isinstance(manifest,list):
        return ['illustrations 必须是配图清单']
    for item in manifest:
        if not isinstance(item,dict) or not item.get('path') or not item.get('prompt'):
            errors.append('illustrations 每项必须有 path 与图片生成提示 prompt')
            continue
        if item['path'] in declared:
            errors.append('配图清单中路径重复')
        declared[item['path']]=item['prompt']
    used=set()
    for i,s in enumerate(ep.get('segments',[])):
        if s.get('reading')!='example':continue
        path=s.get('illustration')
        try:
            resolved=image_path(path)
            if path not in declared:
                raise ValueError('配图未在 illustrations 中登记生成提示')
            with Image.open(resolved) as im:
                if min(im.size)<256:raise ValueError('配图分辨率过低')
                im.verify()
            used.add(path)
        except (ValueError,OSError) as exc:
            errors.append(f'第 {i} 句配图错误：{exc}')
    if not used:
        errors.append('新版学习期至少需要一个带配图的例句')
    return errors


def source_hash(path,ep):
    digest=hashlib.sha256(Path(path).read_bytes())
    if ep.get('format_version')==3:
        for name in ('video.py','episode_assets.py'):
            digest.update((ROOT/name).read_bytes())
        for value in sorted({s['illustration'] for s in ep['segments'] if s.get('illustration')}):
            digest.update(value.encode());digest.update(image_path(value).read_bytes())
    return digest.hexdigest()[:16]

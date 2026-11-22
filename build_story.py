"""Build English-only, multi-voice stories with bilingual sentence cards.

See STORY_GUIDE.md. This tool never publishes to the podcast feed.
"""
import argparse
import asyncio
import hashlib
import json
import math
import re
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from video import wrap

ROOT = Path(__file__).resolve().parent
DEFAULT_VOICES = {
    'Narrator': 'en-US-JennyNeural', 'Mia': 'en-US-AvaNeural',
    'Rosa': 'en-US-EmmaNeural', 'Ben': 'en-US-AndrewNeural',
    'Daniel': 'en-US-GuyNeural',
}
SIZES = {'portrait': (720, 1280), 'landscape': (1280, 720)}
BG, CARD, TEXT, MUTED, ACCENT = '#11151b', '#1d2430', '#f0f4fa', '#bac2cf', '#b6a4df'


def number(value, lower, upper, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lower <= value <= upper:
        raise ValueError(f'{name} must be between {lower} and {upper}')


def clean(text):
    return text.translate(str.maketrans({'’': "'", '“': '"', '”': '"'})).strip()


def unquote(text):
    text = text.strip()
    if len(text) >= 2 and (text[0], text[-1]) in [('“', '”'), ('"', '"')]:
        return text[1:-1].strip()
    return text


def display_text(segment, lang):
    text = unquote(segment[lang])
    if lang == 'en':
        text = clean(text)
    if segment['speaker'] != 'Narrator':
        return f'"{text}"' if lang == 'en' else f'“{text}”'
    return text


def validate(story):
    if story.get('schema_version') != 1:
        raise ValueError('schema_version must be 1')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,100}', story.get('id', '')):
        raise ValueError('id must be a safe filename slug')
    for field in ('title', 'title_zh'):
        if not isinstance(story.get(field), str) or not story[field].strip():
            raise ValueError(f'missing {field}')
    if story.get('orientation', 'portrait') not in (*SIZES, 'both'):
        raise ValueError('orientation must be portrait, landscape, or both')
    if story.get('theme', 'dark') != 'dark':
        raise ValueError('only the dark theme is supported')
    number(story.get('speed', 0.8), 0.5, 1.2, 'speed')
    number(story.get('pause', 0.6), 0, 5, 'pause')
    voices = DEFAULT_VOICES | story.get('voices', {})
    for speaker, voice in voices.items():
        if not isinstance(speaker, str) or not isinstance(voice, str) or not voice.startswith('en-') or not voice.endswith('Neural'):
            raise ValueError(f'invalid English voice for {speaker}')
    segments = story.get('segments')
    if not isinstance(segments, list) or not segments:
        raise ValueError('segments must be a nonempty list')
    for i, segment in enumerate(segments, 1):
        if segment.get('speaker') not in voices:
            raise ValueError(f'segment {i}: unknown speaker')
        for lang in ('en', 'zh'):
            if not isinstance(segment.get(lang), str) or not unquote(segment[lang]):
                raise ValueError(f'segment {i}: missing {lang}')
        if re.search(r'[\u3400-\u9fff]', segment['en']):
            raise ValueError(f'segment {i}: Chinese in spoken English')
        number(segment.get('pause', story.get('pause', 0.6)), 0, 5, f'segment {i} pause')
    return voices


@lru_cache(maxsize=128)
def font(size, bold=False):
    filename = 'NotoSansSC-Bold.otf' if bold else 'NotoSansSC-Regular.otf'
    return ImageFont.truetype(str(ROOT / 'fonts' / filename), size)


def draw_lines(draw, lines, x, y, f, color, spacing=1.5):
    for line in lines:
        draw.text((x, y), line, font=f, fill=color)
        y += f.size * spacing
    return y


def render_card(story, segment, index, total, orientation, destination):
    w, h = SIZES[orientation]
    im = Image.new('RGB', (w, h), BG)
    d = ImageDraw.Draw(im)
    d.text((52, 26), f'ENGLISH STORY  /  {story.get("speed", 0.8):g}x', font=font(17), fill=ACCENT)
    title_lines = wrap(clean(story['title']), font(28, True), w - 104)
    y = draw_lines(d, title_lines, 52, 64, font(28, True), TEXT, 1.3)
    y = draw_lines(d, wrap(story['title_zh'], font(21), w - 104), 52, y + 9, font(21), MUTED, 1.35)
    top, bottom = max(y + 30, 250 if orientation == 'portrait' else 175), h - 120
    d.rounded_rectangle((40, top, w - 40, bottom), radius=24, fill=CARD)
    speaker = segment['speaker'] + (' / 旁白' if segment['speaker'] == 'Narrator' else '')
    d.text((68, top + 24), speaker, font=font(19, True), fill=ACCENT)
    width, available = w - 136, bottom - top - 116
    for size in range(36, 19, -1):
        ef, zf = font(size, True), font(max(20, round(size * 0.78)))
        en = wrap(display_text(segment, 'en'), ef, width)
        zh = wrap(display_text(segment, 'zh'), zf, width)
        need = len(en) * ef.size * 1.5 + len(zh) * zf.size * 1.5 + 44
        if need <= available:
            break
    else:
        raise ValueError(f'segment {index+1} does not fit {orientation}; split the sentence card')
    y = draw_lines(d, en, 68, top + 68, ef, TEXT)
    d.line((68, y + 12, w - 68, y + 12), fill='#384253', width=1)
    y = draw_lines(d, zh, 68, y + 36, zf, MUTED)
    if y > bottom - 20:
        raise ValueError(f'segment {index+1}: subtitle overflow')
    d.text((52, h - 88), f'{index+1:02d} / {total:02d}  ·  English narration / 中英字幕', font=font(17), fill=MUTED)
    d.rounded_rectangle((52, h - 38, w - 52, h - 34), radius=2, fill='#384253')
    d.rounded_rectangle((52, h - 38, 52 + (w - 104) * (index+1) / total, h - 34), radius=2, fill=ACCENT)
    im.save(destination)


def run(*args):
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f'{args[0]} failed:\n{result.stderr[-4000:]}')
    return result.stdout


def duration(path):
    return float(run('ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=nw=1:nk=1', str(path)).strip())


async def make_audio(story, voices, cache, tmp):
    import edge_tts
    speed = story.get('speed', 0.8)
    rate = f'{round((speed - 1) * 100):+d}%'
    available = {v['ShortName'] for v in await edge_tts.list_voices()}
    used = {voices[s['speaker']] for s in story['segments']}
    if not used <= available:
        raise ValueError(f'voices unavailable: {used - available}')
    cache.mkdir(parents=True, exist_ok=True)
    # Group identical requests to avoid racing on the same cache entry.
    requests = {}
    keys = []
    for s in story['segments']:
        voice, text = voices[s['speaker']], clean(unquote(s['en']))
        key = hashlib.sha256(json.dumps([1, voice, rate, text], ensure_ascii=False).encode()).hexdigest()
        keys.append(key)
        requests[key] = (voice, text)
    sem = asyncio.Semaphore(3)

    async def synth(key, voice, text):
        target = cache / f'{key}.mp3'
        if target.exists():
            try:
                if duration(target) > 0:
                    return
            except (ValueError, RuntimeError):
                pass
        async with sem:
            for attempt in range(4):
                with tempfile.NamedTemporaryFile(dir=cache, suffix='.mp3', delete=False) as handle:
                    partial = Path(handle.name)
                try:
                    await edge_tts.Communicate(text, voice, rate=rate).save(str(partial))
                    if duration(partial) <= 0:
                        raise RuntimeError('empty TTS audio')
                    partial.replace(target)
                    return
                except Exception:
                    if attempt == 3:
                        raise
                    await asyncio.sleep(2 * (attempt + 1))
                finally:
                    partial.unlink(missing_ok=True)
    await asyncio.gather(*(synth(key, *req) for key, req in requests.items()))
    print(f'Audio ready: {len(keys)} segments, {len(used)} voices', flush=True)
    timeline, start = [], 0.0
    for i, (s, key) in enumerate(zip(story['segments'], keys)):
        wav = tmp / f'{i:04d}.wav'
        pause = s.get('pause', story.get('pause', 0.6))
        # Native slow speech: no atempo, pitch shift, or time stretching.
        run('ffmpeg', '-y', '-i', str(cache / f'{key}.mp3'), '-af', f'apad=pad_dur={pause}', '-ar', '24000', '-ac', '1', str(wav))
        length = duration(wav)
        timeline.append(dict(s, start=start, end=start+length, voice=voices[s['speaker']]))
        start += length
    (tmp / 'audio.txt').write_text(''.join(f"file '{i:04d}.wav'\n" for i in range(len(keys))))
    return timeline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('story', type=Path)
    parser.add_argument('--orientation', choices=[*SIZES, 'both'])
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'dist' / 'stories')
    parser.add_argument('--cache-dir', type=Path, default=ROOT / '.cache' / 'story-tts')
    parser.add_argument('--preview-segments', type=int)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--render-only', action='store_true', help='Generate all subtitle cards without TTS')
    args = parser.parse_args()
    story = json.loads(args.story.read_text(encoding='utf-8'))
    voices = validate(story)
    if args.preview_segments is not None:
        if args.preview_segments < 1:
            parser.error('--preview-segments must be positive')
        story['segments'] = story['segments'][:args.preview_segments]
    orientation = args.orientation or story.get('orientation', 'portrait')
    orientations = list(SIZES) if orientation == 'both' else [orientation]
    # Render all cards as part of validation: missing glyphs/overflow should fail before synthesis.
    from fontTools.ttLib import TTFont
    glyphs = set(TTFont(ROOT / 'fonts' / 'NotoSansSC-Regular.otf').getBestCmap())
    for s in story['segments']:
        text = display_text(s, 'en') + display_text(s, 'zh') + s['speaker'] + clean(story['title']) + story['title_zh']
        missing = {ch for ch in text if not ch.isspace() and ord(ch) not in glyphs}
        if missing:
            raise ValueError(f'unsupported subtitle characters: {missing}')
    output = args.output_dir.resolve() / story['id']
    if not args.check:
        output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='story-') as folder:
        tmp = Path(folder)
        for orient in orientations:
            dest = (output / f'cards-{orient}') if args.render_only else (tmp / orient)
            if args.check:
                dest = tmp / orient
            dest.mkdir(parents=True, exist_ok=True)
            for i, s in enumerate(story['segments']):
                render_card(story, s, i, len(story['segments']), orient, dest / f'{i:04d}.png')
        if args.check or args.render_only:
            print('OK: story structure, voices, and subtitle layouts', flush=True)
            return
        timeline = asyncio.run(make_audio(story, voices, args.cache_dir.resolve(), tmp))
        (output / 'timeline.json').write_text(json.dumps({'story':story, 'timeline':timeline}, ensure_ascii=False, indent=2), encoding='utf-8')
        audio = output / f'{story["id"]}.m4a'
        run('ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', str(tmp / 'audio.txt'), '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11', '-c:a', 'aac', '-b:a', '192k', str(audio))
        for orient in orientations:
            card_dir = tmp / orient
            concat = card_dir / 'frames.txt'
            concat.write_text(''.join(f"file '{i:04d}.png'\nduration {t['end']-t['start']:.6f}\n" for i,t in enumerate(timeline)) + f"file '{len(timeline)-1:04d}.png'\n")
            video = output / f'{story["id"]}-{orient}.mp4'
            run('ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', str(concat), '-i', str(audio), '-t', str(timeline[-1]['end']), '-vf', 'fps=10,format=yuv420p', '-c:v', 'libx264', '-preset', 'veryfast', '-tune', 'stillimage', '-crf', '23', '-c:a', 'copy', '-movflags', '+faststart', str(video))
            Image.open(card_dir / '0000.png').save(output / f'{orient}-preview.png')
            print(f'Built {video} ({timeline[-1]["end"]:.1f}s)', flush=True)


if __name__ == '__main__':
    main()

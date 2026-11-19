"""把 episodes/*.json 讲解稿合成为 MP3 和竖屏视频，并生成播客 RSS 和网页。

- 每个片段用对应语言的母语神经网络声音朗读（微软 Edge 语音），片段间插入精确停顿。
- 音频和视频永久存放在 GitHub Releases（每期一个 release，tag = 期号），不进 git 仓库。
- 最近 KEEP_ON_SITE 期的媒体文件会复制进网站目录 site/，由 GitHub Pages 提供（正确的
  MIME 类型和断点续传），播客订阅也只列这些期。
- docs/ 里只提交小文件：每期的时间轴 JSON、封面缩略图、feed、网页。
"""
import asyncio
import email.utils
import glob
import hashlib
import html
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone

BASE_URL = "https://xiagughw.github.io/news-vocab-podcast"
DOCS = "docs"            # 提交到仓库的小文件
DIST = "dist"            # 本次生成 / 下载的媒体（不提交）
SITE = "site"            # 部署到 Pages 的完整网站（不提交）
KEEP_ON_SITE = 30
MEDIA_VERSION = 2        # 改了音频或画面的生成方式时加 1，所有期会重新生成

VOICES = {"zh": "zh-CN-XiaoxiaoNeural", "en": "en-US-AvaNeural", "de": "de-DE-KatjaNeural"}
RATE = {"zh": "-8%", "en": "-10%", "de": "-10%"}          # 正常讲解语速
SLOW = {"zh": "-20%", "en": "-30%", "de": "-30%"}         # 单词、短语慢读
DEFAULT_PAUSE = 0.45
SR = 24000
IN_CI = bool(os.environ.get("GITHUB_ACTIONS"))


def is_slow(seg):
    if "slow" in seg:
        return bool(seg["slow"])
    # 英语、德语的短词组默认慢读
    return seg["l"] in ("en", "de") and len(seg["t"].split()) <= 4


async def tts(text, lang, slow, path):
    import edge_tts
    last = None
    for attempt in range(4):
        try:
            c = edge_tts.Communicate(text, VOICES[lang], rate=(SLOW if slow else RATE)[lang])
            await c.save(path)
            if os.path.getsize(path) > 0:
                return
        except Exception as e:  # 网络偶尔失败，重试
            last = e
        await asyncio.sleep(2 * (attempt + 1))
    raise RuntimeError(f"TTS failed for {text!r}: {last}")


def run(*args, **kw):
    return subprocess.run(args, check=True, capture_output=True, text=True, **kw)


def to_wav(src, dst):
    run("ffmpeg", "-y", "-i", src, "-ar", str(SR), "-ac", "1", "-c:a", "pcm_s16le", dst)


def silence(sec, dst):
    run("ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r={SR}:cl=mono",
        "-t", f"{sec:.2f}", "-c:a", "pcm_s16le", dst)


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", path], capture_output=True, text=True).stdout
    return float(out.strip())


def slug_of(ep):
    return ep.get("id", ep["date"])


def pub_of(ep):
    return ep.get("pub") or ep["date"] + "T06:00:00+01:00"


def synth_audio(ep, mp3):
    tmp = tempfile.mkdtemp()
    parts, cues, t = [], [], 0.0
    lead = os.path.join(tmp, "lead.wav")
    silence(0.6, lead)
    parts.append(lead)
    t += 0.6
    for i, seg in enumerate(ep["segments"]):
        raw = os.path.join(tmp, f"{i}.mp3")
        wav = os.path.join(tmp, f"{i}.wav")
        asyncio.run(tts(seg["t"], seg["l"], is_slow(seg), raw))
        to_wav(raw, wav)
        d = duration(wav)
        cues.append({"start": round(t, 2), "l": seg["l"], "t": seg["t"]})
        parts.append(wav)
        t += d
        p = float(seg.get("p", DEFAULT_PAUSE))
        if p > 0:
            s = os.path.join(tmp, f"{i}_s.wav")
            silence(p, s)
            parts.append(s)
            t += p
    lst = os.path.join(tmp, "list.txt")
    with open(lst, "w") as f:
        for p in parts:
            f.write(f"file '{p}'\n")
    run("ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst,
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-ar", "44100", "-ac", "1", "-c:a", "libmp3lame", "-b:a", "64k", mp3)
    shutil.rmtree(tmp)
    return cues


def release_upload(ep, files):
    """上传到这一期的 release（没有就新建）。只在 GitHub Actions 里执行。"""
    if not IN_CI:
        print("  (本地运行，跳过上传)")
        return
    slug = slug_of(ep)
    exists = subprocess.run(["gh", "release", "view", slug], capture_output=True).returncode == 0
    if exists:
        run("gh", "release", "upload", slug, *files, "--clobber")
    else:
        run("gh", "release", "create", slug, *files, "--title", ep["title"],
            "--notes", ep.get("summary", ""), "--latest=false")


def release_download(slug):
    if not IN_CI:
        return False
    r = subprocess.run(["gh", "release", "download", slug, "-D", DIST, "--clobber",
                        "-p", f"{slug}.mp3", "-p", f"{slug}.mp4"], capture_output=True)
    return r.returncode == 0


def build_episode(ep, src_hash):
    import video
    slug = slug_of(ep)
    meta_path = os.path.join(DOCS, "episodes", f"{slug}.json")
    if os.path.exists(meta_path):
        old = json.load(open(meta_path))
        if old.get("src_hash") == src_hash and old.get("v") == MEDIA_VERSION:
            return False
    print("build", slug, flush=True)
    mp3 = os.path.join(DIST, f"{slug}.mp3")
    mp4 = os.path.join(DIST, f"{slug}.mp4")
    cues = synth_audio(ep, mp3)
    meta = {"v": MEDIA_VERSION, "src_hash": src_hash, "duration": round(duration(mp3)),
            "size": os.path.getsize(mp3), "cues": cues}
    print("  video", slug, flush=True)
    video.make_video(ep, meta, mp3, mp4, poster=os.path.join(DOCS, "episodes", f"{slug}.jpg"))
    meta["video_size"] = os.path.getsize(mp4)
    meta["built"] = datetime.now(timezone.utc).isoformat()
    release_upload(ep, [mp3, mp4])
    json.dump(meta, open(meta_path, "w"), ensure_ascii=False, indent=1)
    return True


def hms(sec):
    sec = int(sec)
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def transcript_html(meta):
    tag = {"zh": "中", "en": "EN", "de": "DE"}
    rows = []
    for c in meta["cues"]:
        m, s = divmod(int(c["start"]), 60)
        rows.append(f"[{m}:{s:02d}] {tag[c['l']]} · {html.escape(c['t'])}")
    return "<br>".join(rows)


def episode_desc(ep, meta):
    words = "<br>".join(f"{html.escape(w['en'])} · {html.escape(w['de'])} · {html.escape(w['zh'])}"
                        for w in ep.get("words", []))
    src = "".join(f'<br><a href="{html.escape(s["url"])}">{html.escape(s["name"])}</a>'
                  for s in ep.get("sources", []))
    return (f"<p>{html.escape(ep.get('summary', ''))}</p><p><b>今天的词</b><br>{words}</p>"
            f"<p><b>讲解稿</b><br>{transcript_html(meta)}</p><p><b>新闻来源</b>{src}</p>")


def feed_xml(entries, kind):
    is_video = kind == "video"
    items = []
    for ep, meta in entries:
        slug = slug_of(ep)
        ext, mime, size = ("mp4", "video/mp4", meta.get("video_size", 0)) if is_video else \
                          ("mp3", "audio/mpeg", meta["size"])
        desc = episode_desc(ep, meta)
        items.append(f"""<item>
<title>{html.escape(ep['title'])}</title>
<guid isPermaLink="false">news-vocab-{slug}{'-video' if is_video else ''}</guid>
<pubDate>{email.utils.format_datetime(datetime.fromisoformat(pub_of(ep)))}</pubDate>
<enclosure url="{BASE_URL}/media/{slug}.{ext}" length="{size}" type="{mime}"/>
<itunes:image href="{BASE_URL}/episodes/{slug}.jpg"/>
<itunes:duration>{hms(meta['duration'])}</itunes:duration>
<itunes:summary>{html.escape(ep.get('summary', ''))}</itunes:summary>
<description><![CDATA[{desc}]]></description>
<content:encoded><![CDATA[{desc}]]></content:encoded>
</item>""")
    title = "新闻难词 · 每日三语" + ("（视频）" if is_video else "播客")
    path = "video.xml" if is_video else "feed.xml"
    now = email.utils.format_datetime(datetime.now(timezone.utc))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:content="http://purl.org/rss/1.0/modules/content/" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
<title>{title}</title>
<link>{BASE_URL}/</link>
<atom:link href="{BASE_URL}/{path}" rel="self" type="application/rss+xml"/>
<language>zh-cn</language>
<description>每天从英语和德语的同题热点新闻里挑几个难词，用中文讲解，英语和德语母语声音朗读，适合边做家务边听。</description>
<itunes:author>新闻难词</itunes:author>
<itunes:image href="{BASE_URL}/cover.png"/>
<itunes:category text="Education"><itunes:category text="Language Learning"/></itunes:category>
<itunes:explicit>false</itunes:explicit>
<itunes:type>episodic</itunes:type>
<lastBuildDate>{now}</lastBuildDate>
{''.join(items)}
</channel>
</rss>
"""


def index_html(entries):
    cards = []
    for ep, meta in entries:
        slug = slug_of(ep)
        words = "".join(f"<li><b class=en>{html.escape(w['en'])}</b> · <span class=de>"
                        f"{html.escape(w['de'])}</span> · {html.escape(w['zh'])}</li>"
                        for w in ep.get("words", []))
        cards.append(f"""<section><h2>{html.escape(ep['title'])}</h2>
<video controls playsinline preload="none" poster="episodes/{slug}.jpg" src="media/{slug}.mp4"></video>
<p><a href="media/{slug}.mp3">只听音频（MP3）</a></p>
<p>{html.escape(ep.get('summary', ''))}</p><ul>{words}</ul>
<details><summary>讲解稿</summary><p class=tr>{transcript_html(meta)}</p></details></section>""")
    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>新闻难词 · 每日三语播客</title>
<style>body{{margin:0;background:#111214;color:#ededed;font-family:-apple-system,"PingFang SC",sans-serif;padding:18px;line-height:1.6;max-width:720px;margin:auto}}
h1{{font-size:24px}}h2{{font-size:18px;color:#d9b45a}}section{{background:#1b1c20;border-radius:14px;padding:14px;margin:16px 0}}
video{{width:100%;max-height:80vh;background:#000;border-radius:10px}}a{{color:#86b8ff}}.en{{color:#86b8ff}}.de{{color:#f2b46d}}
code{{word-break:break-all;color:#f2b46d}}.tr{{color:#8d9098;font-size:14px}}summary{{cursor:pointer;color:#8d9098}}
.btn,.btn2{{display:block;text-align:center;padding:14px;margin:10px 0;border-radius:12px;font-weight:600;text-decoration:none}}
.btn{{background:#d9b45a;color:#111}}.btn2{{background:#2a2b30;color:#ededed}}</style></head><body>
<h1>新闻难词 · 每日三语播客</h1>
<p class=sub>
<a class=btn href="{BASE_URL.replace('https://', 'podcasts://')}/feed.xml">在“播客”App 订阅 · 音频版</a>
<a class=btn href="{BASE_URL.replace('https://', 'podcasts://')}/video.xml">在“播客”App 订阅 · 视频版</a>
<a class=btn2 href="overcast://x-callback-url/add?url={BASE_URL}/feed.xml">用 Overcast 订阅</a></p>
<p class=tr>按钮打不开时，手动添加（资料库 → ⋯ → 通过 URL 关注节目）：<br>
音频版 <code>{BASE_URL}/feed.xml</code><br>视频版 <code>{BASE_URL}/video.xml</code></p>
{''.join(cards)}</body></html>"""


def main():
    os.makedirs(os.path.join(DOCS, "episodes"), exist_ok=True)
    os.makedirs(DIST, exist_ok=True)
    shutil.copy("cover.png", os.path.join(DOCS, "cover.png"))
    open(os.path.join(DOCS, ".nojekyll"), "w").close()
    # 旧版本把 MP3 放在 docs 里，现在改存 Releases
    for old in glob.glob(os.path.join(DOCS, "episodes", "*.mp3")):
        os.remove(old)

    episodes = []
    for path in sorted(glob.glob("episodes/*.json")):
        raw = open(path, "rb").read()
        ep = json.loads(raw)
        build_episode(ep, hashlib.sha256(raw).hexdigest()[:16])
        episodes.append(ep)
    episodes.sort(key=pub_of, reverse=True)

    # 网站：最近 KEEP_ON_SITE 期，媒体文件放进 site/media
    shutil.rmtree(SITE, ignore_errors=True)
    shutil.copytree(DOCS, SITE)
    os.makedirs(os.path.join(SITE, "media"), exist_ok=True)
    entries = []
    for ep in episodes:
        if len(entries) >= KEEP_ON_SITE:
            break
        slug = slug_of(ep)
        have = all(os.path.exists(os.path.join(DIST, f"{slug}.{x}")) for x in ("mp3", "mp4"))
        if not have and not release_download(slug):
            print("  缺少媒体文件，跳过", slug)
            continue
        for x in ("mp3", "mp4"):
            shutil.copy(os.path.join(DIST, f"{slug}.{x}"), os.path.join(SITE, "media", f"{slug}.{x}"))
        entries.append((ep, json.load(open(os.path.join(DOCS, "episodes", f"{slug}.json")))))

    for name, content in (("feed.xml", feed_xml(entries, "audio")),
                          ("video.xml", feed_xml(entries, "video")),
                          ("index.html", index_html(entries))):
        for root in (DOCS, SITE):
            open(os.path.join(root, name), "w").write(content)
    print(f"site: {len(entries)} 期")


if __name__ == "__main__":
    main()

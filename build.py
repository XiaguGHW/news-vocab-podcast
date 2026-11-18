"""把 episodes/*.json 讲解稿合成为 MP3，并生成播客 RSS 和网页。

每个片段用对应语言的母语神经网络声音朗读（微软 Edge 语音），
片段之间插入精确的停顿，最后拼成一个 MP3。
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

import edge_tts

BASE_URL = "https://xiagughw.github.io/news-vocab-podcast"
OUT = "docs"

VOICES = {"zh": "zh-CN-XiaoxiaoNeural", "en": "en-US-AvaNeural", "de": "de-DE-KatjaNeural"}
RATE = {"zh": "-8%", "en": "-10%", "de": "-10%"}          # 正常讲解语速
SLOW = {"zh": "-20%", "en": "-30%", "de": "-30%"}         # 单词、短语慢读
DEFAULT_PAUSE = 0.45
SR = 24000


def is_slow(seg):
    if "slow" in seg:
        return bool(seg["slow"])
    # 英语、德语的短词组默认慢读
    return seg["l"] in ("en", "de") and len(seg["t"].split()) <= 4


async def tts(text, lang, slow, path):
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


def run(*args):
    subprocess.run(args, check=True, capture_output=True)


def to_wav(src, dst):
    run("ffmpeg", "-y", "-i", src, "-ar", str(SR), "-ac", "1", "-c:a", "pcm_s16le", dst)


def silence(sec, dst):
    run("ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r={SR}:cl=mono",
        "-t", f"{sec:.2f}", "-c:a", "pcm_s16le", dst)


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", path], capture_output=True, text=True).stdout
    return float(out.strip())


def build_episode(ep, src_hash):
    slug = ep["date"]
    mp3 = os.path.join(OUT, "episodes", f"{slug}.mp3")
    meta_path = os.path.join(OUT, "episodes", f"{slug}.json")
    if os.path.exists(mp3) and os.path.exists(meta_path):
        if json.load(open(meta_path)).get("src_hash") == src_hash:
            print("skip", slug)
            return
    print("build", slug)
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
    os.makedirs(os.path.dirname(mp3), exist_ok=True)
    run("ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst,
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-ar", "44100", "-ac", "1", "-c:a", "libmp3lame", "-b:a", "64k", mp3)
    meta = {"src_hash": src_hash, "duration": round(duration(mp3)),
            "size": os.path.getsize(mp3), "cues": cues,
            "built": datetime.now(timezone.utc).isoformat()}
    json.dump(meta, open(meta_path, "w"), ensure_ascii=False, indent=1)
    shutil.rmtree(tmp)


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


def build_site(episodes):
    items, cards = [], []
    for ep in episodes:
        slug = ep["date"]
        meta = json.load(open(os.path.join(OUT, "episodes", f"{slug}.json")))
        url = f"{BASE_URL}/episodes/{slug}.mp3"
        pub = datetime.fromisoformat(ep["date"] + "T06:00:00+01:00")
        words = " · ".join(f"{w['en']} / {w['de']} / {w['zh']}" for w in ep.get("words", []))
        src = "".join(f'<br><a href="{html.escape(s["url"])}">{html.escape(s["name"])}</a>'
                      for s in ep.get("sources", []))
        desc = (f"<p>{html.escape(ep.get('summary', ''))}</p><p><b>今天的词：</b>{html.escape(words)}</p>"
                f"<p><b>讲解稿</b><br>{transcript_html(meta)}</p><p><b>新闻来源</b>{src}</p>")
        items.append(f"""<item>
<title>{html.escape(ep['title'])}</title>
<guid isPermaLink="false">news-vocab-{slug}</guid>
<pubDate>{email.utils.format_datetime(pub)}</pubDate>
<enclosure url="{url}" length="{meta['size']}" type="audio/mpeg"/>
<itunes:duration>{hms(meta['duration'])}</itunes:duration>
<itunes:summary>{html.escape(ep.get('summary', ''))}</itunes:summary>
<description><![CDATA[{desc}]]></description>
<content:encoded><![CDATA[{desc}]]></content:encoded>
</item>""")
        cards.append(f"""<section><h2>{html.escape(ep['title'])}</h2>
<audio controls preload="none" src="episodes/{slug}.mp3"></audio>{desc}</section>""")
    now = email.utils.format_datetime(datetime.now(timezone.utc))
    feed = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:content="http://purl.org/rss/1.0/modules/content/" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
<title>新闻难词 · 每日三语播客</title>
<link>{BASE_URL}/</link>
<atom:link href="{BASE_URL}/feed.xml" rel="self" type="application/rss+xml"/>
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
    open(os.path.join(OUT, "feed.xml"), "w").write(feed)
    page = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>新闻难词 · 每日三语播客</title>
<style>body{{margin:0;background:#111214;color:#ededed;font-family:-apple-system,"PingFang SC",sans-serif;padding:18px;line-height:1.6}}
h1{{font-size:24px}}h2{{font-size:19px;color:#d9b45a}}section{{background:#1b1c20;border-radius:14px;padding:14px;margin:16px 0}}
audio{{width:100%}}a{{color:#86b8ff}}code{{word-break:break-all;color:#f2b46d}}</style></head><body>
<h1>新闻难词 · 每日三语播客</h1>
<p>订阅地址（在“播客”App 里添加）：<br><code>{BASE_URL}/feed.xml</code></p>
{''.join(cards)}</body></html>"""
    open(os.path.join(OUT, "index.html"), "w").write(page)


def main():
    os.makedirs(os.path.join(OUT, "episodes"), exist_ok=True)
    shutil.copy("cover.png", os.path.join(OUT, "cover.png"))
    open(os.path.join(OUT, ".nojekyll"), "w").close()
    episodes = []
    for path in sorted(glob.glob("episodes/*.json")):
        raw = open(path, "rb").read()
        ep = json.loads(raw)
        build_episode(ep, hashlib.sha256(raw).hexdigest()[:16])
        episodes.append(ep)
    episodes.sort(key=lambda e: e["date"], reverse=True)
    build_site(episodes)


if __name__ == "__main__":
    main()

"""根据讲解稿和音频时间轴，生成竖屏视频（1080x1920）。

画面：顶部进度条 → 当前词卡片（英语 / 德语 / 中文 + 图标）→ 滚动字幕。
跟读、测验的停顿时间里显示提示。
"""
import os
import re
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
BG = (17, 18, 20)
CARD = (29, 30, 35)
LINE = (46, 48, 55)
TEXT = (237, 237, 237)
MUTED = (141, 144, 152)
GOLD = (217, 180, 90)
EN = (134, 184, 255)
DE = (242, 180, 109)
OK = (127, 212, 154)
LANG_COLOR = {"zh": TEXT, "en": EN, "de": DE}
LANG_TAG = {"zh": "中", "en": "EN", "de": "DE"}

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_B = os.path.join(HERE, "fonts", "NotoSansSC-Bold.otf")
FONT_R = os.path.join(HERE, "fonts", "NotoSansSC-Regular.otf")
FONT_E = os.path.join(HERE, "fonts", "NotoColorEmoji.ttf")
FONT_IPA = os.path.join(HERE, "fonts", "DejaVuSans.ttf")
_cache = {}


def font(size, bold=True):
    key = (size, bold)
    if key not in _cache:
        _cache[key] = ImageFont.truetype(FONT_B if bold else FONT_R, size)
    return _cache[key]


def ipa_font(size):
    key = ("ipa", size)
    if key not in _cache:
        _cache[key] = ImageFont.truetype(FONT_IPA, size)
    return _cache[key]


_emoji_font = None


def emoji_img(ch, size):
    """单个 emoji 渲染成 size×size 的图。"""
    global _emoji_font
    if _emoji_font is None:
        _emoji_font = ImageFont.truetype(FONT_E, 109)
    im = Image.new("RGBA", (136, 128), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((0, 0), ch, font=_emoji_font, embedded_color=True)
    box = im.getbbox()
    if box:
        im = im.crop(box)
    im.thumbnail((size, size), Image.LANCZOS)
    return im


def emoji_list(s):
    return [c for c in (s or "") if c not in "️‍" and not c.isspace()]


def wrap(text, f, width):
    """按宽度换行：中文按字，西文按词。"""
    tokens = re.findall(r"[A-Za-zÀ-ÿ0-9'’\-]+[.,!?;:]?|\s+|.", text)
    lines, cur = [], ""
    for t in tokens:
        test = cur + t
        if f.getlength(test) <= width or not cur:
            cur = test
        else:
            lines.append(cur.rstrip())
            cur = t.lstrip()
    if cur.strip():
        lines.append(cur.rstrip())
    # 中文标点不放在行首
    for k in range(1, len(lines)):
        while lines[k] and lines[k][0] in "，。、：；！？）」』”’…":
            lines[k - 1] += lines[k][0]
            lines[k] = lines[k][1:]
    return [l for l in lines if l]


def fit(text, size, width, bold=True):
    """字太长就缩小字号，保证一行放得下。"""
    while size > 18 and font(size, bold).getlength(text) > width:
        size -= 2
    return font(size, bold)


def rounded(d, box, fill, r=28, outline=None, width=0):
    d.rounded_rectangle(box, r, fill=fill, outline=outline, width=width)


def pill(d, x, y, lang, rep=None):
    f = font(30)
    t = LANG_TAG[lang] + (f" {['', '0.6×', '0.6×', '0.8×'][rep]}" if rep else "")
    w = f.getlength(t) + 28
    rounded(d, (x, y, x + w, y + 46), (42, 44, 50) if lang == "zh" else
            ((29, 44, 68) if lang == "en" else (58, 42, 23)), r=10)
    d.text((x + 14, y + 4), t, font=f, fill=LANG_COLOR[lang])
    return w


def draw_text_block(d, x, y, text, f, fill, width, gap=10, max_y=None):
    lines = wrap(text, f, width)
    for n, line in enumerate(lines):
        if max_y and y + f.size > max_y:
            break
        if max_y and n + 1 < len(lines) and y + 2 * f.size + gap > max_y:
            line = line[:-1] + "…"
        d.text((x, y), line, font=f, fill=fill)
        y += f.size + gap
    return y


def paste_emojis(im, s, x, y, size, gap=24):
    for ch in emoji_list(s):
        e = emoji_img(ch, size)
        im.paste(e, (int(x), int(y + (size - e.height) / 2)), e)
        x += size + gap
    return x


def header(d, ep, sec, n_words):
    d.text((60, 52), "新闻难词", font=font(46), fill=GOLD)
    d.text((280, 60), ep.get("date", ""), font=font(36, False), fill=MUTED)
    # 进度点：开场 · 词1..n · 测验
    steps = ["intro"] + list(range(1, n_words + 1)) + ["quiz"]
    step = min(44, (W - 560) // len(steps))
    x = W - 60 - len(steps) * step
    for s in steps:
        on = (s == sec) or (sec == "review" and s == "intro")
        c = GOLD if on else LINE
        if isinstance(s, int):
            d.ellipse((x, 70, x + 28, 98), fill=c)
        else:
            d.rounded_rectangle((x, 76, x + 28, 92), 8, fill=c)
        x += step
    d.line((60, 140, W - 60, 140), fill=LINE, width=2)


def card_intro(im, d, ep, sec, seen):
    rounded(d, (60, 180, W - 60, 980), CARD)
    if sec == "review":
        d.text((110, 220), "复习上一期", font=font(44), fill=GOLD)
        y = 320
        for c in seen:
            if c["l"] in ("en", "de"):
                d.text((110, y), c["t"], font=font(64), fill=LANG_COLOR[c["l"]])
                y += 96
            elif c["l"] == "zh" and len(c["t"]) <= 12:
                d.text((110, y), c["t"].rstrip("。"), font=font(54), fill=TEXT)
                y += 90
        return
    d.text((110, 220), ep.get("topic", "今天的新闻"), font=font(40), fill=GOLD)
    if ep.get("pic"):
        paste_emojis(im, ep["pic"], 110, 300, 150)
    title = re.sub(r"^.*?·\s*", "", ep["title"]).split("｜")[0]
    y = draw_text_block(d, 110, 490, title, font(60), TEXT, W - 220, 16)
    draw_text_block(d, 110, y + 30, ep.get("summary", ""), font(36, False), MUTED, W - 220, 14, max_y=950)


def word_line(d, y, text, f, color, ipa, ipa_size, width):
    """一行单词，音标放在右边；放不下就放到下一行。返回下一行的 y。"""
    x = 110
    lines = wrap(text, f, width)
    for ln in lines:
        d.text((x, y), ln, font=f, fill=color)
        last_w = f.getlength(ln)
        y += int(f.size * 1.18)
    if ipa:
        fi = ipa_font(ipa_size)
        iw = fi.getlength(ipa)
        if x + last_w + 28 + iw <= W - 110:
            top = y - int(f.size * 1.18)
            d.text((x + last_w + 28, top + int(f.size * 0.92) - int(ipa_size * 0.95)), ipa, font=fi, fill=MUTED)
        else:
            d.text((x, y + 4), ipa, font=fi, fill=MUTED)
            y += int(ipa_size * 1.5)
    return y


def card_word(im, d, ep, k):
    """词卡：英语 + 音标、德语 + 音标、中文。返回卡片底部的 y。"""
    w = ep["words"][k - 1]
    n = len(ep["words"])
    d.text((110, 196), f"第 {k} / {n} 个词", font=font(34), fill=GOLD)
    y = 262
    en_size = 96 if len(w["en"]) <= 12 else (78 if len(w["en"]) <= 20 else 64)
    y = word_line(d, y, w["en"], font(en_size), EN, w.get("ipa"), 40, W - 220)
    y = word_line(d, y + 6, w["de"], font(54), DE, None, 34, W - 220)
    d.line((110, y + 14, W - 110, y + 14), fill=LINE, width=2)
    y = draw_text_block(d, 110, y + 32, w["zh"], font(44), TEXT, W - 220, 8)
    bottom = y + 22
    card = Image.new("RGB", (W - 120, bottom - 170), CARD)
    return bottom


def draw_word_card(im, d, ep, k):
    # 先量出高度，再画背景，最后画内容
    probe = Image.new("RGB", (W, H))
    bottom = card_word(probe, ImageDraw.Draw(probe), ep, k)
    rounded(d, (60, 170, W - 60, bottom), CARD)
    d.rectangle((60, 170, 72, bottom), fill=GOLD)
    w = ep["words"][k - 1]
    if w.get("pic"):
        paste_emojis(im, w["pic"], W - 110 - 2 * 88 - 16, 182, 88, gap=16)
    card_word(im, d, ep, k)
    return bottom


def examples_panel(d, items, cur, top, bottom):
    """本词出现过的例句：外语句子 + 中文意思，当前这句高亮。"""
    if not items:
        return
    d.text((70, top), "例句", font=font(32), fill=GOLD)
    top += 56
    fs, fz = font(40), font(34, False)
    tw = W - 70 - 150 - 40

    def height(it):
        h = len(wrap(it["t"], fs, tw)) * (fs.size + 10)
        if it["zh_shown"] and it["zh"]:
            h += len(wrap(it["zh"], fz, tw)) * (fz.size + 8) + 4
        return h + 30

    show = list(range(len(items)))
    while show and sum(height(items[j]) for j in show) > bottom - top:
        show.pop(0)
    y = top
    for j in show:
        it = items[j]
        on = j == cur
        if on:
            d.rectangle((60, y - 6, 66, y + height(it) - 30), fill=GOLD)
        pill(d, 80, y + 2, it["l"])
        color = LANG_COLOR[it["l"]] if (on or cur is None) else tuple(int(c * 0.62) for c in LANG_COLOR[it["l"]])
        for ln in wrap(it["t"], fs, tw):
            d.text((160, y), ln, font=fs, fill=color)
            y += fs.size + 10
        if it["zh_shown"] and it["zh"]:
            y += 4
            for ln in wrap(it["zh"], fz, tw):
                d.text((160, y), ln, font=fz, fill=TEXT if on else MUTED)
                y += fz.size + 8
        y += 30


def subtitle_line(d, cue, top, bottom):
    """词卡模式下的底部字幕：只显示正在读的这一句。"""
    d.line((60, top - 16, W - 60, top - 16), fill=LINE, width=2)
    f = font(46 if cue["l"] == "zh" else 44)
    pw = pill(d, 60, top + 6, cue["l"], cue.get("rep"))
    lines = wrap(cue["t"], f, W - 60 - (60 + pw + 20))
    y = top
    for ln in lines[:3]:
        d.text((60 + pw + 20, y), ln, font=f, fill=LANG_COLOR[cue["l"]])
        y += f.size + 12


def card_quiz(im, d, ep, revealed):
    rounded(d, (60, 180, W - 60, 980), CARD)
    d.text((110, 215), "小测验", font=font(48), fill=GOLD)
    d.text((300, 228), "先在心里说出英语和德语", font=font(34, False), fill=MUTED)
    words = ep["words"]
    if len(words) <= 5:
        y = 320
        for i, w in enumerate(words):
            d.text((110, y), w["zh"], font=fit(w["zh"], 48, 430), fill=TEXT)
            if i < revealed:
                d.text((560, y - 6), w["en"], font=fit(w["en"], 40, W - 110 - 560), fill=EN)
                d.text((560, y + 44), w["de"], font=fit(w["de"], 34, W - 110 - 560, False), fill=DE)
            else:
                d.text((560, y + 10), "？", font=font(48), fill=LINE)
            y += 128
        return
    h = (950 - 310) / len(words)
    y = 310
    for i, w in enumerate(words):
        zh = w["zh"].split("（")[0]
        d.text((110, y), zh, font=fit(zh, int(h * 0.5), 360), fill=TEXT)
        if i < revealed:
            d.text((490, y - 2), w["en"], font=fit(w["en"], int(h * 0.38), W - 110 - 490), fill=EN)
            d.text((490, y + h * 0.42), w["de"], font=fit(w["de"], int(h * 0.32), W - 110 - 490, False), fill=DE)
        else:
            d.text((490, y), "？", font=font(int(h * 0.5)), fill=LINE)
        y += h


def subtitles(d, cues, i):
    """当前句大字，上面两句变暗。"""
    top, bottom = 1030, 1800
    d.line((60, top - 20, W - 60, top - 20), fill=LINE, width=2)
    cur = cues[i]
    f = font(64 if cur["l"] == "zh" else 62)
    cur_lines = wrap(cur["t"], f, W - 120 - (170 if cur.get("rep") else 90))
    cur_h = len(cur_lines) * (f.size + 14)
    y0 = bottom - cur_h
    # 之前的句子
    prev_f = font(38, False)
    y = y0 - 40
    prev = []
    j = i - 1
    while j >= 0 and len(prev) < 2:
        if cues[j]["t"] != cur["t"] and (not prev or cues[j]["t"] != cues[prev[-1]]["t"]):
            prev.append(j)
        j -= 1
    for j in prev:
        lines = wrap(cues[j]["t"], prev_f, W - 120 - 90)
        h = len(lines) * (prev_f.size + 10)
        if y - h < top:
            break
        y -= h
        pill(d, 60, y + 2, cues[j]["l"])
        yy = y
        for ln in lines:
            d.text((150, yy), ln, font=prev_f, fill=MUTED)
            yy += prev_f.size + 10
        y -= 26
    pw = pill(d, 60, y0 + 12, cur["l"], cur.get("rep"))
    yy = y0
    tx = 150 if not cur.get("rep") else 60 + pw + 20
    for ln in cur_lines:
        d.text((tx, yy), ln, font=f, fill=LANG_COLOR[cur["l"]])
        yy += f.size + 14


def badge(im, d, kind):
    if kind == "think":
        e, t, c = "🤔", "想一想：英语？德语？", GOLD
    else:
        e, t, c = "🗣", "轮到你跟读", OK
    rounded(d, (60, 1810, W - 60, 1890), (34, 36, 41), r=24)
    paste_emojis(im, e, 90, 1820, 60)
    d.text((180, 1822), t, font=font(44), fill=c)


def recall_state(sec, n_words):
    if not isinstance(sec, str):
        return None
    kind, _, value = sec.partition(":")
    if kind in ("recall", "answer") and value.isdigit() and 1 <= int(value) <= n_words:
        return kind, int(value)
    return None


def card_recall(im, d, ep, state, cue):
    """独立回忆画面不绘制词卡、历史例句或历史字幕，避免泄露答案。"""
    kind, k = state
    rounded(d, (60, 180, W - 60, 1720), CARD)
    d.text((110, 230), "回忆练习" if kind == "recall" else "参考答案", font=font(48), fill=GOLD)
    d.text((110, 320), f"第 {k} 个词", font=font(36), fill=MUTED)
    if kind == "recall":
        draw_text_block(d, 110, 470, cue["t"], font(52), TEXT, W - 220, 18, max_y=1500)
        d.text((110, 1550), "先想一想，再听答案", font=font(40), fill=GOLD)
    else:
        w = ep["words"][k - 1]
        y = word_line(d, 470, w["en"], font(70), EN, w.get("ipa"), 38, W - 220)
        y = word_line(d, y + 30, w["de"], font(50), DE, None, 34, W - 220)
        draw_text_block(d, 110, y + 30, w["zh"], font(44), TEXT, W - 220, 14, max_y=1200)
        subtitle_line(d, cue, 1400, 1650)


def render_frames(ep, meta, outdir):
    """返回 [(png路径, 时长秒), ...]"""
    segs = ep["segments"]
    cues = meta["cues"]
    total = meta["duration"]
    n_words = len(ep.get("words", []))
    frames = []
    sec = "intro"
    sec_start = 0
    quiz_en = 0
    items, cur_item = [], None
    for i, (seg, cue) in enumerate(zip(segs, cues)):
        if "sec" in seg:
            sec = seg["sec"]
            sec_start = i
            items, cur_item = [], None
        if sec == "quiz" and seg["l"] == "en":
            quiz_en += 1
        if seg.get("rep") == 1:
            items.append({"l": seg["l"], "t": seg["t"], "zh": seg.get("zh", ""), "zh_shown": False})
            cur_item = len(items) - 1
        elif seg.get("rep"):
            cur_item = len(items) - 1
        elif seg.get("zh_for") and items:
            items[-1]["zh_shown"] = True
            cur_item = len(items) - 1
        else:
            cur_item = None
        nxt = cues[i + 1]["start"] if i + 1 < len(cues) else total
        p = float(seg.get("p", 0.45))
        speak_end = max(cue["start"] + 0.3, nxt - p) if p >= 2 else nxt
        for phase in ("speak", "pause") if p >= 2 else ("speak",):
            im = Image.new("RGB", (W, H), BG)
            d = ImageDraw.Draw(im)
            recall = recall_state(sec, n_words)
            header(d, ep, recall[1] if recall else sec, n_words)
            if recall:
                card_recall(im, d, ep, recall, cue)
            elif isinstance(sec, int) and 1 <= sec <= n_words:
                card_bottom = draw_word_card(im, d, ep, sec)
                examples_panel(d, items, cur_item, card_bottom + 34, 1585)
                subtitle_line(d, cue, 1630, 1800)
            else:
                if sec == "quiz":
                    card_quiz(im, d, ep, quiz_en)
                else:
                    card_intro(im, d, ep, sec, cues[sec_start:i + 1])
                subtitles(d, cues, i)
            if phase == "pause":
                badge(im, d, "think" if seg["l"] == "zh" else "shadow")
            path = os.path.join(outdir, f"f{i:04d}_{phase}.png")
            im.save(path)
            if phase == "speak":
                frames.append((path, (speak_end if p >= 2 else nxt) - (cue["start"] if i else 0)))
            else:
                frames.append((path, nxt - speak_end))
    return frames


def make_video(ep, meta, mp3, out_mp4, poster=None):
    tmp = tempfile.mkdtemp()
    frames = render_frames(ep, meta, tmp)
    if poster:
        Image.open(frames[0][0]).convert("RGB").resize((540, 960)).save(poster, quality=80)
    lst = os.path.join(tmp, "frames.txt")
    with open(lst, "w") as f:
        for p, dur in frames:
            f.write(f"file '{p}'\nduration {max(dur, 0.05):.3f}\n")
        f.write(f"file '{frames[-1][0]}'\n")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-i", mp3,
                    "-vf", "fps=10,format=yuv420p", "-c:v", "libx264", "-preset", "medium",
                    "-tune", "stillimage", "-crf", "28", "-c:a", "aac", "-b:a", "80k",
                    "-shortest", "-movflags", "+faststart", out_mp4],
                   check=True, capture_output=True)
    return out_mp4

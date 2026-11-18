"""检查 episodes/*.json 是否符合 EPISODE_GUIDE.md 的硬性规则。用法：python check_episode.py [文件…]"""
import glob
import json
import re
import sys

from fontTools.ttLib import TTFont

FONT_CHARS = set(chr(k) for k in TTFont("fonts/NotoSansSC-Bold.otf").getBestCmap())
EMOJI_CHARS = set(chr(k) for k in TTFont("fonts/NotoColorEmoji.ttf").getBestCmap())

files = sys.argv[1:] or sorted(glob.glob("episodes/*.json"))
errors = []
for f in files:
    try:
        ep = json.load(open(f, encoding="utf-8"))
    except Exception as e:
        errors.append(f"{f}: JSON 格式错误：{e}")
        continue
    for key in ("date", "title", "summary", "words", "segments"):
        if key not in ep:
            errors.append(f"{f}: 缺少字段 {key}")
    if not f.endswith(f"{ep.get('id', ep.get('date'))}.json"):
        errors.append(f"{f}: 文件名和 id/date 不一致")
    for i, s in enumerate(ep.get("segments", [])):
        l, t = s.get("l"), s.get("t", "")
        if l not in ("zh", "en", "de"):
            errors.append(f"{f} 第{i}句: 语言 {l!r} 不对")
        if not t.strip():
            errors.append(f"{f} 第{i}句: 空文本")
        if l == "zh" and re.search(r"[A-Za-zÄÖÜäöüß]", t):
            errors.append(f"{f} 第{i}句: 中文句子里有拉丁字母：{t}")
        if l in ("en", "de") and re.search(r"[一-鿿]", t):
            errors.append(f"{f} 第{i}句: 外语句子里有汉字：{t}")
        missing = {ch for ch in t if ch not in FONT_CHARS and not ch.isspace()}
        if missing:
            errors.append(f"{f} 第{i}句: 字体里没有这些字，视频会显示成方块，请换个常用写法：{''.join(missing)}")
        p = s.get("p", 0.45)
        if not isinstance(p, (int, float)) or not 0 <= p <= 8:
            errors.append(f"{f} 第{i}句: 停顿 p={p!r} 不合理")
    secs = [s.get("sec") for s in ep.get("segments", []) if "sec" in s]
    n = len(ep.get("words", []))
    if ep.get("segments") and secs[:1] != ["intro"]:
        errors.append(f"{f}: 第一句要有 \"sec\": \"intro\"")
    for k in range(1, n + 1):
        if k not in secs:
            errors.append(f"{f}: 缺少第 {k} 个词的开头标记 \"sec\": {k}")
    if n and "quiz" not in secs:
        errors.append(f"{f}: 缺少小测验的开头标记 \"sec\": \"quiz\"")
    for w in ep.get("words", []):
        for ch in (w.get("pic", "") + ep.get("pic", "")):
            if ch in "\ufe0f\u200d" or ch.isspace():
                continue
            if ch not in EMOJI_CHARS:
                errors.append(f"{f}: 图标 {ch!r} 不在 emoji 字体里，换一个")
        for ch in w.get("zh", "") + w.get("de", "") + w.get("en", ""):
            if ch not in FONT_CHARS and not ch.isspace():
                errors.append(f"{f}: 词卡里的字 {ch!r} 字体里没有")
if errors:
    print("\n".join(errors))
    sys.exit(1)
print(f"OK: {len(files)} 个文件")

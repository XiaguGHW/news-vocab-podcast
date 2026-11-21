"""检查 episodes/*.json 是否符合 EPISODE_GUIDE.md 的硬性规则。用法：python check_episode.py [文件…]"""
import glob
import json
import re
import sys

from fontTools.ttLib import TTFont

FONT_CHARS = set(chr(k) for k in TTFont("fonts/NotoSansSC-Bold.otf").getBestCmap())
IPA_CHARS = set(chr(k) for k in TTFont("fonts/DejaVuSans.ttf").getBestCmap())
EMOJI_CHARS = set(chr(k) for k in TTFont("fonts/NotoColorEmoji.ttf").getBestCmap())

def validate_learning(ep):
    """新版教学规范的结构检查；自然程度仍须人工审核。旧稿保持兼容。"""
    if ep.get("format_version") != 2:
        return []
    errors = []
    for key in ("id", "date", "pub", "title", "topic", "summary", "pic", "words", "sources", "segments"):
        if not ep.get(key) and key != "sources":
            errors.append(f"缺少或空字段 {key}")
    words, segs = ep.get("words", []), ep.get("segments", [])
    if not isinstance(words, list) or not isinstance(segs, list):
        return errors + ["words 和 segments 必须是列表"]
    if not 1 <= len(words) <= 11:
        errors.append("新版每期须有 1–11 个词")
    for k, w in enumerate(words, 1):
        for key in ("en", "de", "zh", "ipa", "pic"):
            if not w.get(key):
                errors.append(f"第 {k} 个词缺少 {key}")
        ipa = w.get("ipa", "")
        if not (ipa.startswith("/") and ipa.endswith("/") and len(ipa) > 2):
            errors.append(f"第 {k} 个词音标须写在斜线里")
    # recall:k 提问时隐藏答案，answer:k 首个外语片段开始揭示。
    pending = None
    quizzed = set()
    in_quiz = False
    for i, seg in enumerate(segs):
        sec = seg.get("sec")
        if sec == "quiz":
            in_quiz = True
        if isinstance(sec, str) and sec.startswith(("recall:", "answer:")):
            kind, _, value = sec.partition(":")
            if not value.isdigit() or not 1 <= int(value) <= len(words):
                errors.append(f"第 {i} 句回忆词编号无效")
                continue
            k = int(value)
            if kind == "recall":
                if pending is not None:
                    errors.append("上一道回忆题尚未给出答案")
                pending = k
                if seg.get("l") != "zh" or seg.get("p", 0) < 3:
                    errors.append("回忆题须用中文提问并留至少三秒思考")
                if words[k-1].get("en", "").casefold() in seg.get("t", "").casefold():
                    errors.append("回忆题提前包含英语答案")
            else:
                if pending != k or seg.get("l") != "en":
                    errors.append("答案必须接在对应回忆题之后，并从英语开始")
                if seg.get("t", "").strip().rstrip(".").casefold() != words[k-1].get("en", "").casefold():
                    errors.append("答案须先读词卡中的英语词形")
                following = segs[i + 1] if i + 1 < len(segs) else {}
                if following.get("l") != "de" or following.get("t", "").strip().rstrip(".") != words[k-1].get("de", ""):
                    errors.append("英语答案之后须紧接词卡中的德语对应表达")
                if in_quiz:
                    quizzed.add(k)
                pending = None
        elif pending is not None:
            errors.append("提问与答案之间不能插入其他片段")
        if seg.get("l") in ("en", "de"):
            if not seg.get("t", "").endswith("."):
                errors.append(f"第 {i} 句外语须以句号结束")
            if len(seg.get("t", "").split()) > 4 and not seg.get("zh"):
                errors.append(f"第 {i} 句长外语片段须有中文意思，包括不重复片段")
    if pending is not None:
        errors.append("最后一道回忆题缺少答案")
    if quizzed != set(range(1, len(words)+1)):
        errors.append("结尾小测须逐词使用 recall:k / answer:k 覆盖全部词")
    return errors


def check_files(files):
    errors = []
    for f in files:
        try:
            ep = json.load(open(f, encoding="utf-8"))
        except Exception as e:
            errors.append(f"{f}: JSON 格式错误：{e}")
            continue
        if not isinstance(ep, dict):
            errors.append(f"{f}: 顶层必须是对象")
            continue
        errors.extend(f"{f}: {e}" for e in validate_learning(ep))
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
            if l in ("en", "de") and len(t.split()) > 4 and s.get("repeat", True):
                zh = s.get("zh", "")
                if not zh:
                    errors.append(f"{f} 第{i}句: 英语/德语句子缺少中文意思 \"zh\"：{t}")
                elif re.search(r"[A-Za-zÄÖÜäöüß]", zh):
                    errors.append(f"{f} 第{i}句: \"zh\" 里有拉丁字母：{zh}")
                else:
                    missing_zh = {ch for ch in zh if ch not in FONT_CHARS and not ch.isspace()}
                    if missing_zh:
                        errors.append(f"{f} 第{i}句: \"zh\" 里有字体没有的字：{''.join(missing_zh)}")
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
        needs_ipa = ep.get("date", "") >= "2026-11-21"   # 之前的期数没有音标，不要求
        for w in ep.get("words", []):
            for key in ("ipa",):
                val = w.get(key, "")
                if needs_ipa and not val:
                    errors.append(f"{f}: 词 {w.get('en')!r} 缺少音标 \"{key}\"")
                bad = {ch for ch in val if ch not in IPA_CHARS}
                if bad:
                    errors.append(f"{f}: 词 {w.get('en')!r} 的 {key} 里有字体显示不了的符号：{''.join(bad)}")
            for ch in (w.get("pic", "") + ep.get("pic", "")):
                if ch in "\ufe0f\u200d" or ch.isspace():
                    continue
                if ch not in EMOJI_CHARS:
                    errors.append(f"{f}: 图标 {ch!r} 不在 emoji 字体里，换一个")
            for ch in w.get("zh", "") + w.get("de", "") + w.get("en", ""):
                if ch not in FONT_CHARS and not ch.isspace():
                    errors.append(f"{f}: 词卡里的字 {ch!r} 字体里没有")
    return errors


if __name__ == "__main__":
    errors = check_files(sys.argv[1:] or sorted(glob.glob("episodes/*.json")))
    if errors:
        print("\n".join(errors))
        sys.exit(1)
    print("OK: 检查通过")

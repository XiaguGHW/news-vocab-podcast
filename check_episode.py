"""检查 episodes/*.json 是否符合 EPISODE_GUIDE.md 的硬性规则。用法：python check_episode.py [文件…]"""
import glob
import json
import re
import sys

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
    if not f.endswith(f"{ep.get('date')}.json"):
        errors.append(f"{f}: 文件名和 date 不一致")
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
        p = s.get("p", 0.45)
        if not isinstance(p, (int, float)) or not 0 <= p <= 8:
            errors.append(f"{f} 第{i}句: 停顿 p={p!r} 不合理")
if errors:
    print("\n".join(errors))
    sys.exit(1)
print(f"OK: {len(files)} 个文件")

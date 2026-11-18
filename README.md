# 新闻难词 · 每日三语播客

每天从英语和德语的同题热点新闻里挑几个难词，中文讲解，英语和德语用母语神经网络声音朗读，适合边做家务边听。

- 订阅地址（在 iPhone“播客”App 里添加）：`https://xiagughw.github.io/news-vocab-podcast/feed.xml`
- 网页版（带讲解稿）：https://xiagughw.github.io/news-vocab-podcast/

## 工作原理

1. `episodes/YYYY-MM-DD.json`：每期讲解稿，按句标注语言和停顿。写法见 `EPISODE_GUIDE.md`。
2. `build.py`：用微软 Edge 神经网络语音（中文 Xiaoxiao、英语 Ava、德语 Katja）逐句合成，插入停顿，拼成 MP3，并生成 `docs/feed.xml` 和 `docs/index.html`。
3. `.github/workflows/build.yml`：每次推送讲解稿后自动运行 `build.py`，并发布到 GitHub Pages。

# 新闻难词 · 每日三语播客

每天从英语和德语的同题热点新闻里挑几个难词，中文讲解，英语和德语用母语神经网络声音朗读，适合边做家务边听。

- 音频订阅（iPhone“播客”App → 资料库 → ⋯ → 通过 URL 关注节目）：`https://xiagughw.github.io/news-vocab-podcast/feed.xml`
- 视频订阅：`https://xiagughw.github.io/news-vocab-podcast/video.xml`
- 网页版（带讲解稿）：https://xiagughw.github.io/news-vocab-podcast/

## 工作原理

1. `episodes/YYYY-MM-DD.json`：每期讲解稿，按句标注语言和停顿。写法见 `EPISODE_GUIDE.md`。
2. `build.py`：用微软 Edge 神经网络语音（中文 Xiaoxiao、英语 Ava、德语 Katja）逐句合成，插入停顿，拼成 MP3；`video.py` 按时间轴生成竖屏视频（词卡 + 滚动字幕 + 跟读提示）。
3. 媒体文件永久存在 GitHub Releases（每期一个），最近 30 期同时放在 GitHub Pages 上供播放和订阅；仓库里只提交时间轴、缩略图、feed 和网页。
4. `.github/workflows/build.yml`：每次推送讲解稿后自动运行 `check_episode.py` 和 `build.py`，并发布到 GitHub Pages。
5. `fonts/`：思源黑体简体（常用字子集）和 Noto 彩色 emoji，用于视频画面。

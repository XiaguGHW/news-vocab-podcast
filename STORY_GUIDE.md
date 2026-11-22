# 英语多角色故事视频

这是独立于三语词汇讲解的期型。仅朗读英文，每段一次；中文只作字幕。
默认深色画面，直接由语音服务生成约 0.8 倍自然慢速，不对音频做后期拉慢。
语速是语音服务的相对设置，不承诺不同声音具有完全相同的每分钟词数。

## 写作与声音

- 先写自然、合理、能让人放松的故事；生词使用常见搭配，不强行凑词。正式词放在工作、行政等适当场景。
- 中文逐句对应英文；先人工审核语言与剧情，再运行程序检查。通过程序检查不等于语言已审核。
- 每段只有一个说话人。人物直接引语和 `she said` 等旁白应分成不同片段。旁白片段的角色必须为 `Narrator`。
- 人物台词在画面上自动加英文双引号、中文引号；旁白不加。稿件内无需手工重复加引号，也不在音频中念角色名。
- 每段一般一句；紧密相连的短句可以合成一张卡。太长放不下时程序报错，不截断正文。
- 默认使用已确认音色：旁白 Jenny、Mia Ava、Rosa Emma、Ben Andrew、Daniel Guy，均为美式英文声音。
- 新角色需要在 `voices` 中明确分配英文声音。角色应始终使用同一音色。

## 故事稿格式

在 `stories/` 中创建新 JSON，文件名与 `id` 相同；不覆盖已有故事，除非用户明确要求修改。
`id` 使用字母、数字、连字符或下划线。示例见 `stories/mia-weekend-preview.json`。

```json
{
  "schema_version": 1,
  "id": "my-new-story",
  "title": "A Quiet Afternoon",
  "title_zh": "安静的午后",
  "theme": "dark",
  "orientation": "portrait",
  "speed": 0.8,
  "pause": 0.6,
  "voices": {"Mia": "en-US-AvaNeural"},
  "segments": [
    {"speaker": "Narrator", "en": "Mia opened the window.", "zh": "米娅打开了窗。"},
    {"speaker": "Mia", "en": "What a lovely day.", "zh": "天气真好。", "pause": 0.8}
  ]
}
```

`orientation` 可以是 `portrait`（竖屏 720×1280）、`landscape`（横屏 1280×720）、`both`（两版）。省略时默认竖屏。两种布局独立排版，不裁切或拉伸画面。
`speed` 默认 0.8，支持 0.5–1.2；`pause` 是句后停顿秒数，默认 0.6。
中文姓名默认用米娅，英文用 Mia。

## 本地生成

需要 Python 3.12、ffmpeg / ffprobe，以及：

```bash
python3 -m pip install edge-tts pillow fonttools
python3 build_story.py stories/mia-weekend-preview.json --check --orientation both
python3 build_story.py stories/mia-weekend-preview.json --orientation portrait
python3 build_story.py stories/mia-weekend-preview.json --orientation landscape
python3 build_story.py stories/mia-weekend-preview.json --orientation both
```

- `--preview-segments 12` 只生成前十二个片段；输出到单独目录可以保留不同试听版本：`--output-dir dist/preview`。
- `--render-only` 只生成全部字幕图片，无需联网或调用语音服务。
- `--check` 校验结构、字体覆盖和所选画幅的全部字幕排版，不联网。
- 输出目录默认为 `dist/stories/<id>/`，包含 MP4、M4A、时间轴 JSON 和封面预览。
- `.cache/story-tts/` 缓存原始语音，按英文文本、声音和语速标识。改中文、改画幅或换主题不重新合成相同语音；改英文、声音或语速会生成新的缓存。
- 导出 AAC 192 kbps 不意味着提高语音服务源音频的固有质量；重点是避免时间拉伸和多轮有损编码。

## GitHub Actions

**Build story video** 在 `stories/` 等相关文件推送时自动生成。仅修改故事稿时，只处理本次变化的稿件；删除的稿件不生成。
手动运行可选择稿件路径和 `portrait / landscape / both / from-file`，并设置试听片段数。
自动生成采用稿件内的 `orientation`；手动选项可以覆盖。

运行完成后在该次 Actions 的 **Artifacts** 下载 `story-videos`，包含生成的视频、音频和时间轴。附件保留九十天；需要长期收藏时下载保存。
这一步不更新播客源、网站或 Releases。发布需要用户另外明确要求。

### 经用户明确同意后发布全文

仅在用户明确要求发布时，在故事 JSON 增加 `"publish": true`、`date`（当天柏林日期）和带时区的 `pub`。
`id` 必须与故事文件名一致，且不能与已有播客期数重复。可选 `podcast_title`；默认显示中文故事标题与期型。
发布采用 `orientation`，若为 `both`，默认以竖屏进入播客；可用 `podcast_orientation` 明确选择。
**build podcast** 会生成故事、上传 MP3 和 MP4 到独立 Release，将其加入现有音频源与视频源并部署网站。
以后的普通词汇期构建也会保留已批准的故事。试听稿默认不发布。
MP3 从原始句段音频直接编码，不从已压缩的 M4A 再转换；保留英文多角色音色，中文仅用于字幕与讲解稿。
确认 Actions 成功、线上音频源及视频源都含本期后，才能报告发布成功。

批准发布的故事还必须提供 `words`：明确列出本期目标词的 `en`、`zh`、`de`，建议附 `ipa`；词形需要时提供 `lemma` 或 `forms`。不用为故事中全部英文词建词条。
用户已授权发布后自动将此表同步到统一生词本；与现有词去重、遵守排除项、不伪造练习或掌握。发布流程最后的词汇同步步骤也必须成功。

## 交付检查

1. 检查说话人分配、英文台词、中文译文和人物引号。
2. 对所需画幅运行 `--check`；抽看长句和短句画面。
3. 实际生成并用 ffprobe 确认画幅、时长及音视频流；完整解码检查媒体完整性。
4. 告知用户时长、画幅、语速以及是否已发布；不要把生成附件说成已发布到播客。

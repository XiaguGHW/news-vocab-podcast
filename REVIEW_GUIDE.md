# 图片回忆复习期

纯复习期使用 `reviews/<id>.json`，与完整讲解期和英语故事分开。
每个目标词一张清晰场景图，图片帮助理解当前例句，并不穷尽词义。

- 先中文情境提问；读完问题后留三秒，显示三、二、一倒计时。思考期间隐藏外语答案、图片和例句。
- 揭晓时直接显示英语词形、美式音标、中文、当前语境的德语对应、场景图及中英例句，不加过渡卡。
- 英语答案、德语对应、中文核心义各读一次；例句英语原生 0.8 倍两遍、0.9 倍一遍，最后中文一遍。不是后期拉慢。
- 使用自然常用搭配，问题明确词性与当前目标义；允许相关词有其他合理答案。
- 同源名词和形容词分开提问。易混词用当前句子明确语境。
- 复习源 `words` 必含 `learning_id`、`en`、`de`、`zh`、`ipa`、`question`、`example`、`translation`、`image`。`spoken` 可单独指定词组的可朗读形式。
- `image` 只能引用仓库的 `assets/review/`；保存图片生成提示 `image_prompt`，便于后续复用或修订。
- 每期包含 `id`、`date`、带时区的 `pub`、`title`、`summary`、`schema_version:1`。只有用户授权发布时才设 `publish:true`。

本地检查：`python build_review.py reviews/<id>.json --check`。
生成：`python build_review.py reviews/<id>.json`，默认深色竖屏 720×1280；输出 MP3、MP4 和时间轴到 `dist/reviews/<id>/`。
原始语音在 `.cache/review-tts/` 缓存；修改图片、字幕不重新请求相同语音。

发布复用现有音频源、视频源与网站，媒体放在同一期 Release。
确认 Actions 成功、音视频源包含本期、词汇同步步骤成功后，才能报告已发布。
发布同步只补词条来源，保留已有练习历史与复习日期，不推断用户已观看或答对。

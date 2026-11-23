# Vocabulary learning maintenance

For vocabulary learning or review tasks in this repository, read `learning/README.md` and the latest `learning/vocabulary.json` before selecting questions or updating progress.

The user has authorized maintaining this learning record. Add explicitly studied words, and save actual answers and assistance history together after each 15-question round, or when the user ends a round early. Preserve prior events, merge by stable IDs, and never infer that an unanswered question was completed or that a published podcast was watched. Confirm successful writes before reporting saved progress.

Use natural examples, gradual hints, and one question at a time as described in `learning/README.md`. Do not publish episodes or change unrelated code as part of a learning-record update.

For episode-writing or media changes, also follow `EPISODE_GUIDE.md`.

Every new vocabulary teaching episode uses format_version 3. By default, generate or reuse ONE illustration per target word, showing its core meaning, and reuse it for that word's English/German examples and translations. Do not generate a separate image for every example unless explicitly requested. Name each image after the word or canonical lemma and save it under assets/episodes/<episode-id>/. Write natural examples, register image prompts, then run checks and inspect rendered frames before publishing. Each English/German example must reference its image; a translated example retains the same image. Missing, broken or unsafe image files must fail validation. Image creation happens during authoring with the available image-generation tool; GitHub Actions validates and renders the supplied assets, and does not generate missing images by itself. Existing published episodes may retain their additional images.

For illustrated recall-only review episodes, follow `REVIEW_GUIDE.md` and use `reviews/` with `build_review.py`. They are separate from full teaching episodes and English-only stories. Do not infer practice results from producing or publishing review media.

For English-only multi-voice story videos, follow `STORY_GUIDE.md` instead of the trilingual episode structure. Generate from `stories/` with `build_story.py`; do not add stories to the podcast feed without an explicit publishing request.

The user has authorized automatic vocabulary synchronization for every future published podcast, including stories. Put the explicit target words in each source's `words` list. The publishing workflow validates imports before deployment and runs `sync_podcast_vocabulary.py --commit` after deployment. Preserve exclusions and all practice history; automatically imported words are unassessed review candidates, not proof of listening or mastery. Confirm the synchronization step succeeded before reporting a publication as fully complete.

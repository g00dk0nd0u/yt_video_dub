# Translation Mode

This document is for the translation step only. Keep general development rules in `AGENTS.md`.

## Goals

- Treat this as dubbing translation, not subtitle translation.
- Preserve the source meaning.
- Produce natural, conversational Japanese.
- Prefer concise spoken phrasing over literal translation.
- Keep the translation short enough to be read within the specified duration.
- Avoid unnecessary subjects, repetition, and verbose expressions.

## Structural Rules

- Do not break the timestamp structure.
- Preserve line count.
- Preserve chunk number.
- Preserve segment ID, start, end, and duration values exactly; never edit them to
  make a translation fit.
- Keep the original ordering.

## Content Rules

- Preserve technical terms and proper nouns unless there is a strong reason to localize them.
- Do not invent missing details.
- Do not silently omit uncertain parts.
- Keep wording compact enough for spoken delivery.

## Output Discipline

- Return only the translated content in the required format.
- Do not add commentary inside the translated file.
- If a source line is ambiguous, keep the ambiguity rather than guessing.

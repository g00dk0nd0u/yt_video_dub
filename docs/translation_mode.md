# Translation Mode

This document is for the translation step only. Keep general development rules in `AGENTS.md`.

## Goals

- Preserve the source meaning.
- Produce natural Japanese.
- Prefer short lines that are easy for TTS to read.
- Avoid stiff literal translation.

## Structural Rules

- Do not break the timestamp structure.
- Preserve line count.
- Preserve chunk number.
- Preserve segment ID.
- Preserve start, end, and duration values exactly.
- Keep the original ordering.

## Content Rules

- Preserve proper nouns unless there is a strong reason to localize them.
- Do not invent missing details.
- Do not silently omit uncertain parts.
- Keep wording compact enough for spoken delivery.

## Output Discipline

- Return only the translated content in the required format.
- Do not add commentary inside the translated file.
- If a source line is ambiguous, keep the ambiguity rather than guessing.

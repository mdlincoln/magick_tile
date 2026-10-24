# AGENTS.md

Repository-specific guidance for agents working in this project.

## Changelog

`CHANGELOG.md` records changes to what the tool writes: the generated directory
layout and the `info.json` payload, with whatever a consumer has to do about it
(usually "regenerate existing trees"). It is not a record of documentation work.
Do not add entries for edits to `README.md` or any other doc, and do not describe
the README's content or its relationship to the changelog from inside the
changelog — a reader consulting it is asking what the output used to be.

Documentation changes belong in their own commit, described by its message.

## README

`README.md` stays high level about operating the library: install, run, the
output tree for Image API 3.0, development, releasing. Version-specific naming
for 2.1 and the history of breaking changes live in `CHANGELOG.md`, which the
README links to. `tests/test_meta.py` pins both ends of that split — the README
must mention `--version` and link `CHANGELOG.md`, and the changelog must name
both canonical size-directory forms (`w,h`, `w,`) and both full-size keywords
(`full/max`, `full/full`).

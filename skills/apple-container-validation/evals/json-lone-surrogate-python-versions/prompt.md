---
tags: [apple-container-validation]
max_turns: 80
timeout_seconds: 1800
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

同僚が「Python の json.loads は "\\ud800" みたいな対になってない surrogate のエスケープを含む JSON をエラーにせず受け入れる。3.12 でも 3.13 でも同じ」って言ってるんだけど本当？Mac に Apple Container 入ってるので、python:3.12-slim と python:3.13-slim で実際に動かして確かめて、レポートを outputs/ に残して。

# Upstream components

Source: https://github.com/zjunlp/predict-before-execute

Commit: `c4d52cf99bd870d830b456ac7c0684aec1aef375`

The following files are copied without modification:

- `grade/util/prompt.py` → `prompt.py` (prompt construction and response parsing)
- `grade/util/eval.py` → `eval.py` (accuracy metric)
- `LICENSE` → `LICENSE` (MIT)

The smoke runner calls these components directly. It adapts only the API transport to SiliconFlow, sets explicit output limits, and disables retries. It does not run the entire upstream CLI or execute candidate solutions.

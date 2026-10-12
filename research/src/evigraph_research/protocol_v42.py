"""Frozen protocol 4.2: LLM-paraphrased copies (H6).

Registered on 2026-10-12, after the protocol 4.1 results and before any paraphrase was
generated. Protocol 4.0 found a danger zone: copies with 5-30% of tokens replaced by random
words evade MinHash, cosine and containment attribution yet still raise the risk of naive kNN.
Random substitution is artificial; this protocol asks the same question for paraphrases
written by an LLM, the realistic way to produce a reworded copy.

Setting: the protocol 4.0 final_test targets (seed 10) and their sources; m = COPIES copies per
source; systems, thresholds, attribution methods and thresholds exactly as in protocol 4.0.
EUR-Lex texts (CC BY 4.0) are sent to the DeepSeek API with the user's permission.
"""

PROTOCOL_VERSION = "4.2"
FROZEN_ON = "2026-10-12"
SEEDS = (0, 1, 2)
COPIES = 100
VARIANTS = 5  # distinct paraphrases per source and level; each is copied COPIES // VARIANTS times
MAX_SOURCE_CHARS = 6000  # sources are cut at the last whitespace before this many characters

# Generation (OpenAI-compatible chat completions)
API_BASE = "https://api.deepseek.com"
MODEL = "deepseek-flash"
TEMPERATURE = 1.0
MAX_OUTPUT_TOKENS = 4096
RETRIES = 3
# Amendment before any paraphrase was generated (2026-10-12): deepseek-flash reasons by
# default, and in a smoke test all output tokens went to reasoning with an empty answer.
# Reasoning is disabled; it is not needed for paraphrasing.
THINKING = {"type": "disabled"}
SYSTEM = "You are a careful legal editor. Output only the requested text, without comments."
PROMPTS = {
    "paraphrase_light": (
        "Rewrite the following legal text with light edits: replace some words with "
        "synonyms and slightly rephrase some sentences, but keep the structure, all legal "
        "terms, references, numbers and dates.\n\nTEXT:\n"
    ),
    "paraphrase_full": (
        "Paraphrase the following legal text thoroughly: rewrite every sentence in your own "
        "words and change the sentence structure, while preserving its meaning, the legal "
        "references, numbers and dates.\n\nTEXT:\n"
    ),
}

# Scenarios (m = COPIES each):
#   exact      - verbatim copies (built-in check: must reproduce the protocol 4.0 result);
#   truncated  - the source cut to MAX_SOURCE_CHARS, verbatim (control for truncation);
#   paraphrase_light / paraphrase_full - VARIANTS LLM paraphrases of the truncated source.
SCENARIOS = ("exact", "truncated", "paraphrase_light", "paraphrase_full")
# A source whose generations fail after RETRIES is dropped from the paraphrase scenarios
# (its copies are not added); the number of dropped sources is reported.

# Decision rule H6 (confirmed with 3 of 3 seeds, alpha = 0.10, final_test targets): for
# paraphrase_full, (i) every attribution method attributes < 50% of copies to their source's
# group, and (ii) the lower bound of the 95% source-clustered interval of the change in
# targeted risk of naive kNN is > 0. Everything else is reported without a rule.
RESULTS_FILE = "protocol_v42_results.json"

# PETS 3.1.3 — roles of supporting evidence sources

This document defines source roles, not permission to reproduce source text.
PETS never copies protected guidance into a Telegram post.  It creates a new
Russian-language draft only from a factual brief with traceable evidence and
always keeps medical claims in review.

| Source | Role in PETS | Automated use | Boundary |
| --- | --- | --- | --- |
| PMC OA / Frontiers via PMC | Primary factual source | Yes, only full text with a verified licence that permits adaptation | Every factual claim retains article URL and section; a single study is not a universal recommendation. |
| WSAVA | Fact-check or manual editorial review | No | Its published guidelines are valuable veterinary context, but PETS does not scrape, copy or adapt them automatically. |
| AAHA | Fact-check or manual editorial review | No | It is used to challenge an unsupported or risky claim, not as a text source for automatic rewriting. |
| Cat Friendly Homes | Fact-check or manual editorial review | No | Owner-facing material can help a human editor assess practical relevance; medical issues remain for a veterinarian. |
| FDA CVM | Safety signal only | Yes, review-only | A recall record is never transformed into an owner recommendation. |

## Why the three guidance sites are not automatic sources

- WSAVA provides professional global guidelines, while its academy terms restrict reproducing,
  modifying and creating derivative works without prior written consent.
- AAHA labels its web information as no replacement for professional advice and retains rights
  in its electronic communications and marks.
- Cat Friendly Homes identifies itself as caregiver information and explicitly says it cannot
  answer individual medical inquiries or replace a veterinarian.

The pipeline therefore records these sites as `fact_check_or_manual_review` only.  It uses no
automated scraper for them and stores no copied article text.

## Image status

`image_search_feasible` only means that a human/editorial image search is plausible for the
animal and household context.  It never means a concrete photograph has been found, licensed or
verified.  `image_verified` remains `false` until the existing image-rights flow records a
specific asset, author, licence, attribution and topical match.

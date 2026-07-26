# AGENTS.md — How AI should use this repository

This repository is a **structured knowledge base of PRC legal texts**, organised by **legal effect hierarchy**.  
Use it for accurate grounding when answering questions about Chinese law.

## 1. Source of truth

| Path | Role |
|------|------|
| `content/` | **Authoritative text.** All converted Markdown lives here. Read only from here when grounding answers. |
| `incoming/` | Temporary drop zone for PDFs. Empty after conversion. Ignore for reasoning. |
| `sources/` | Auxiliary notes (e.g. biji). Secondary; do not treat as primary law. |

Never invent articles. If the needed text is not under `content/`, say so.

## 2. Effect hierarchy (strict, top → bottom)

When texts conflict, **higher rank prevails**. Do not treat lower ranks as equal to higher ones.

```
01_Constitution              宪法          — supreme
02_Statutes                  法律          — NPC / NPCSC
03_Administrative_Regulations 行政法规     — State Council
04_Local_Regulations         地方性法规
05_Judicial_Interpretations  司法解释      — distinct tier, not legislation
06_Authoritative_Cases       指导性案例    — interpretive only
```

Rules of use:

- Prefer the highest applicable rank that addresses the question.
- Judicial interpretations (05) and guiding cases (06) **interpret** statutes; they do not override them.
- Local regulations (04) cannot contradict higher norms.
- Always state the rank when you cite (e.g. “根据《…》（法律）…”).

## 3. How to locate a text

1. Decide the correct rank folder under `content/`.
2. Search by statute name or keyword inside that folder (and higher ranks if needed).
3. Cite with:
   - full title
   - folder rank
   - filename if useful

Example citation style:

> 《中华人民共和国立法法》（法律，`content/02_Statutes/…`）第 × 条……

## 4. What not to do

- Do not flatten the hierarchy (do not treat a regulation as if it were a statute).
- Do not rely on `incoming/` or deleted PDFs.
- Do not invent missing articles or “common knowledge” substitutes when the text is absent.
- Do not use secondary commentary in place of the primary text when the primary text exists here.

## 5. Workflow reminder (for humans / maintainers)

PDFs go into `incoming/<rank>/` → Action converts to `content/<rank>/` → source PDF is deleted.  
Agents only need to read `content/`.

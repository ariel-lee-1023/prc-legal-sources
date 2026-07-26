# PRC Legal Sources

Authoritative legal sources of the People's Republic of China, organised by **legal effect hierarchy**.

Provides accurate grounding for legal AI agents.

> **For AI agents:** start with [`AGENTS.md`](./AGENTS.md) — it tells you how to navigate `content/`, respect the effect hierarchy, and cite correctly.

## Effect hierarchy (top → bottom)

| Folder | Chinese | Nature |
|--------|---------|--------|
| `01_Constitution` | 宪法 | Supreme, unconditioned |
| `02_Statutes` | 法律 | Enacted by NPC / NPCSC |
| `03_Administrative_Regulations` | 行政法规 | Issued by State Council, subordinate to statutes |
| `04_Local_Regulations` | 地方性法规 | Subordinate to above |
| `05_Rules` | 规章 | Departmental / local government rules |
| `06_Judicial_Interpretations` | 司法解释 | Distinct effect-tier, not legislation |
| `07_Authoritative_Cases` | 指导性案例 / 权威案例 | Interpretive, not enacted |
| `08_Judicial_Guidance_Documents` | 司法指导性文件 | Court guidance documents |
| `09_Local_Judicial_Guidance` | 地方司法指导文件 | Local court guidance |
| `10_Other_Authoritative_Materials` | 其他权威材料 | Other authoritative materials |

## How to use (drop-folder workflow)

1. Download the PDFs (from the official database or elsewhere).
2. Upload them into the matching folder under `incoming/`:

```
incoming/
├── 01_Constitution/                 ← 宪法
├── 02_Statutes/                     ← 法律
├── 03_Administrative_Regulations/   ← 行政法规
├── 04_Local_Regulations/            ← 地方性法规
├── 05_Rules/                        ← 规章
├── 06_Judicial_Interpretations/     ← 司法解释
├── 07_Authoritative_Cases/          ← 指导性案例 / 权威案例
├── 08_Judicial_Guidance_Documents/  ← 司法指导性文件
├── 09_Local_Judicial_Guidance/      ← 地方司法指导文件
└── 10_Other_Authoritative_Materials/← 其他权威材料
```

3. Push (or upload via the GitHub web UI).
   The Action will automatically:
   - convert every `*.pdf` (text-layer → Chinese OCR → markitdown fallback)
   - handle dual-column 公报 layout and soft line-wraps
   - write the `.md` files into the corresponding place under `content/`
   - delete the source PDF (keeps the repo light)
   - commit & push the result

You can also trigger it manually: **Actions → Convert incoming legal PDFs → Run workflow**.

## Conversion pipeline

| Stage | Engine | Handles |
|-------|--------|---------|
| 1 | PyMuPDF text layer + dual-column reorder | Official text PDFs |
| 2 | Tesseract `chi_sim` OCR (left→right column split) | Scanned 公报 / image-only PDFs |
| 3 | MarkItDown / pdfminer | Last-resort fallback |

Post-process: fullwidth→halfwidth digits, strip running headers/page numbers, join mid-sentence soft wraps.

**Note:** OCR is slower (roughly 5–15 s/page). Prefer official text-layer PDFs when available.

## Output layout

```
content/
├── 01_Constitution/
├── 02_Statutes/
├── 03_Administrative_Regulations/
├── 04_Local_Regulations/
├── 05_Rules/
├── 06_Judicial_Interpretations/
├── 07_Authoritative_Cases/
├── 08_Judicial_Guidance_Documents/
├── 09_Local_Judicial_Guidance/
└── 10_Other_Authoritative_Materials/
```

## License & Attribution

Content originates from publicly available PRC legal texts. Respect original licenses and attribution where present. This mirror exists for research and AI grounding purposes.

# PRC Legal Sources

Authoritative legal sources of the People's Republic of China, organised by **legal effect hierarchy**.

Provides accurate grounding for legal AI agents.

## Effect hierarchy (top → bottom)

| Folder | Chinese | Nature |
|--------|---------|--------|
| `01_Constitution` | 宪法 | Supreme, unconditioned |
| `02_Statutes` | 法律 | Enacted by NPC / NPCSC |
| `03_Administrative_Regulations` | 行政法规 | Issued by State Council, subordinate to statutes |
| `04_Local_Regulations` | 地方性法规 | Subordinate to above |
| `05_Judicial_Interpretations` | 司法解释 | Distinct effect-tier, not legislation |
| `06_Authoritative_Cases` | 指导性案例 / 权威案例 | Interpretive, not enacted |

## How to use (drop-folder workflow)

1. Download the PDFs (from biji.com or elsewhere).
2. Upload them into the matching folder under `incoming/`:

```
incoming/
├── 01_Constitution/                 ← 宪法 PDFs
├── 02_Statutes/                     ← 法律 PDFs
├── 03_Administrative_Regulations/   ← 行政法规 PDFs
├── 04_Local_Regulations/            ← 地方性法规 PDFs
├── 05_Judicial_Interpretations/     ← 司法解释 PDFs
└── 06_Authoritative_Cases/          ← 指导性案例 PDFs
```

3. Push (or upload via the GitHub web UI).
   The Action will automatically:
   - convert every `*.pdf` with [MarkItDown](https://markitdown.tools/en)
   - write the `.md` files into the corresponding place under `content/`
   - delete the source PDF (keeps the repo light)
   - commit & push the result

You can also trigger it manually: **Actions → Convert incoming legal PDFs → Run workflow**.

## Output layout

```
content/
├── 01_Constitution/
│   └── <original-name>.md
├── 02_Statutes/
│   └── <original-name>.md
├── 03_Administrative_Regulations/
│   └── <original-name>.md
├── 04_Local_Regulations/
│   └── <original-name>.md
├── 05_Judicial_Interpretations/
│   └── <original-name>.md
└── 06_Authoritative_Cases/
    └── <original-name>.md
```

## Notes

- MarkItDown uses pdfminer (text extraction). Scanned / image-only PDFs may need OCR first.
- The old 得到大脑 OpenAPI path is no longer the primary intake — the public API cannot see knowledge-base “文件” PDFs. Use this drop-folder workflow instead.

## License & Attribution

Content originates from publicly available PRC legal texts. Respect original licenses and attribution where present. This mirror exists for research and AI grounding purposes.

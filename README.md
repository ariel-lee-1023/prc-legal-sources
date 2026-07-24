# PRC Legal Sources

Authoritative legal sources of the People's Republic of China: current laws & regulations, judicial interpretations, and guiding cases / precedents.

Provides accurate grounding for legal AI agents.

## Source of Truth

Primary collection lives in Get笔记 (biji.com) knowledge base:

- Topic ID: `LYw7MjpY`
- Title: 公益法律智库
- URL: https://biji.com/topic/LYw7MjpY

This repository is a versioned, searchable, git-backed mirror optimized for AI retrieval and citation.

## Sync Workflow

See [`scripts/sync_from_biji.py`](scripts/sync_from_biji.py) and [`.github/workflows/sync-biji.yml`](.github/workflows/sync-biji.yml).

### Credentials

Required GitHub repository secrets:

- `BIJI_API_KEY`
- `BIJI_CLIENT_ID`

Obtain them at: https://www.biji.com/openapi

### Manual trigger

```bash
# after exporting the secrets locally
python scripts/sync_from_biji.py
```

Or ask Grok: "Run the biji → prc-legal-sources sync"

## Structure

```
sources/
  ├── laws/
  ├── regulations/
  ├── judicial-interpretations/
  ├── guiding-cases/
  └── notes/          # raw notes from the knowledge base (Markdown)
attachments/          # images, PDFs, audio extracted from notes
scripts/
  └── sync_from_biji.py
```

## License & Attribution

Content originates from the 公益法律智库 knowledge base. Respect original licenses and attribution where present. This mirror exists for research and AI grounding purposes.

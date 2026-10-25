# Wally frontend

Next.js 16 interface for Wally. See the [project README](../README.md) for the full documentation.

```bash
npm install
npm run dev        # http://localhost:3000
npm run build      # production build
npm run lint
```

The backend URL defaults to `http://localhost:8001`; override it with `NEXT_PUBLIC_API_BASE`.

| Path | Purpose |
|---|---|
| `app/page.tsx` | App state: health polling, quota, question queue, streaming |
| `app/layout.tsx` | Fonts (Satoshi, local; Figtree, Google) and toast provider |
| `app/globals.css` | Palette tokens and motion |
| `components/Sidebar.tsx` | Navigation, quota and connection status |
| `components/Exchange.tsx` | One question and answer: progress, citations, sources, timing, feedback |
| `components/Markdown.tsx` | Answer renderer with clickable citations |
| `components/DocumentDrawer.tsx` | Chunk preview, statistics, citation map |
| `components/views/*` | Ask, Library, Performance, Knowledge gaps, Settings |
| `lib/api.ts` | Typed API client, SSE parser, upload with progress |

Satoshi is licensed under the ITF Free Font License (Fontshare) and is bundled in `app/fonts/`.

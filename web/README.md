# Web frontend (placeholder)

The SvelteKit + Tailwind + shadcn-svelte frontend lives here from v0.1 onward. Design system: see [`../docs/DESIGN_SYSTEM.md`](../docs/DESIGN_SYSTEM.md) (Bauhaus).

## Planned structure (v0.1)

```
web/
├── package.json
├── svelte.config.js
├── tailwind.config.ts
├── vite.config.ts
├── src/
│   ├── app.html
│   ├── app.css                      # Outfit font import + Bauhaus tokens
│   ├── lib/
│   │   ├── api/                     # FastAPI client wrappers
│   │   ├── components/              # shadcn-svelte + custom Bauhaus components
│   │   │   ├── BauhausButton.svelte
│   │   │   ├── BauhausCard.svelte
│   │   │   └── BauhausGeometricLogo.svelte
│   │   └── stores/                  # Svelte stores for project state
│   ├── routes/
│   │   ├── +layout.svelte           # Nav with geometric logo
│   │   ├── +page.svelte             # Library view (project list)
│   │   ├── projects/
│   │   │   └── [slug]/
│   │   │       └── +page.svelte     # Editor view
│   │   └── settings/
│   │       └── +page.svelte         # Providers / library / preferences
│   └── locales/
│       ├── en.json
│       └── zh-CN.json
└── static/
    └── geometric-shapes.svg
```

## Why SvelteKit

- Smaller bundle than React (better for Tauri webview later)
- Built-in static export (works inside the Python sidecar without a Node runtime in production)
- TypeScript first
- Excellent Tailwind integration

## Running locally (target — v0.1)

```bash
cd web
npm install        # or pnpm
npm run dev        # opens http://localhost:5173, talks to FastAPI on :7681
```

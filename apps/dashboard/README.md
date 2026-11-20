# Dashboard — Dubai Real Estate AI Platform

Internal operations dashboard for the multi-agent AI system (Next.js 14 App Router, React 18, strict TypeScript).
No UI kit, no Tailwind, no chart library: design tokens live in `src/app/globals.css`, components use CSS Modules,
and charts are small hand-written SVG components in `src/components/charts/`.

## Getting started

```bash
cp .env.example .env.local   # set NEXT_PUBLIC_API_BASE_URL
npm install                  # first run also creates package-lock.json (commit it)
npm run dev                  # http://localhost:3000
```

| Script              | Purpose                          |
| ------------------- | -------------------------------- |
| `npm run dev`       | Development server               |
| `npm run build`     | Production build (standalone)    |
| `npm run start`     | Serve the production build       |
| `npm run lint`      | `next lint`                      |
| `npm run typecheck` | `tsc --noEmit`                   |
| `npm run test`      | `vitest run`                     |

## Data honesty

- Every mock record lives in `src/lib/demo-data.ts`. All names, phones (`+971 50 000 00xx`), emails (`@example.com`)
  and projects are fictional, and every page showing them renders a `DemoDataBanner`.
- Demo prices are labelled **illustrative** and are not market data.
- `/agents` and `/workflows` call the backend first (`GET /api/v1/agents`, `GET /api/v1/workflows`, 5 s timeout).
  On success they show **Live from API**; otherwise they show an error state and fall back to demo data.
- The top bar polls `GET /health` and shows API connectivity.
- `/login` is a UI shell only — authentication is **not** wired to the backend yet.

## Layout

```
src/
  app/            App Router: /login, (dashboard) route group with sidebar layout
  components/     layout/, ui/ (state + table + badge components), charts/ (SVG)
  features/       page-level views per domain (agents, workflows, leads, ...)
  hooks/          useApiResource, useApiHealth
  lib/            config, demo-data, formatting, navigation
  services/       api.ts (typed fetch client with timeout)
  types/          backend contract + domain types
```

## Docker

```bash
docker build --build-arg NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 -t dre-dashboard .
docker run -p 3000:3000 dre-dashboard
```

The image runs the Next.js standalone server as a non-root user on port 3000.

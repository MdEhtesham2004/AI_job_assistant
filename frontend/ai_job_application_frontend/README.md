# Frontend — AI Job Application Platform

React 19 + Vite 8, JavaScript (JSX). Architecture: `assets/phase-1/system_architecture.md` §7.

## Run locally

```bash
cd frontend/ai_job_application_frontend
npm install
npm run dev          # http://localhost:5173 — /api is proxied to http://localhost:8000
```

Start the backend first (see `backend/README.md`), or the System Status page shows "unreachable".

## Scripts

| Command | Purpose |
|---|---|
| `npm run dev` | dev server with hot reload |
| `npm test` | run tests once (Vitest + Testing Library) |
| `npm run test:watch` | tests in watch mode |
| `npm run lint` | ESLint |
| `npm run format` | Prettier (write) |
| `npm run build` | production build → `dist/` |

## Structure

```text
src/
├── main.jsx, App.jsx      providers (theme, TanStack Query, router, toasts)
├── routes/routes.jsx      route table (grows per phase)
├── layouts/               AppLayout (sidebar + header), navigation
├── pages/                 one file per route
├── features/<name>/       api.js, hooks/, components/
├── components/ui/         shadcn-style primitives (button, card, badge)
├── components/common/     shared building blocks (PageHeader, StatusBadge)
├── api/                   client.js (fetch wrapper + ApiError), queryKeys, queryClient
├── theme/                 light/dark theme
├── lib/                   utilities
├── styles/index.css       Tailwind + theme variables
└── test/                  test setup and helpers
```

Rules: components never call `fetch` directly — always `api/client.js` through a feature hook.

## Docker

The `Dockerfile` builds the app and serves it with nginx, which also proxies `/api/` to `BACKEND_URL` (default `http://backend:8000`).

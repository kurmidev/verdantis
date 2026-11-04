# Steward UI

Vite + React + TypeScript, TanStack Query/Table/Virtual, plain CSS tokens. Design: `docs/lld/modules/13-steward-ui.md`.

```
npm run dev:mock    # MSW mocks + dev role switcher (no backend needed)
npm run dev         # proxies /api to localhost:8000 (set VITE_DEV_AUTH=true for header auth)
npm run typecheck && npm run lint && npm test && npm run build
npm run e2e         # Playwright + axe against the mocked dev server (npx playwright install chromium first)
```

Config (`.env.example`): `VITE_API_BASE` (single base URL), `VITE_USE_MOCKS`, `VITE_DEV_AUTH`. Real OIDC is not built (OQ-800).
Mocks (`src/mocks`) follow the LLD 04/11 contract; `GET /batches` and `GET /exports/{id}` are provisional there (OQ-810, OQ-132).

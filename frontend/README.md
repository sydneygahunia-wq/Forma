# Forma frontend

Next.js 16 storefront and live warehouse dashboard. See the [root README](../README.md) for setup and [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) for design.

```bash
npm run dev        # http://localhost:3000 (expects the API on :8000)
npm test           # Vitest unit tests
npm run e2e        # Playwright; boots its own API + production build
npm run lint && npm run typecheck
```

Set `NEXT_PUBLIC_API_URL` to point at a different API (inlined at build time).

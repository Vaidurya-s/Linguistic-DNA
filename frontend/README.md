# Frontend

React + TypeScript + Vite, with Tailwind CSS. Graph rendering (Cytoscape.js) arrives in roadmap Week 4.

```bash
npm install
npm run dev        # http://localhost:5173, proxies /api to http://localhost:8000
npm run lint       # oxlint
npm test           # vitest
npm run build      # typecheck + production build
```

Set `VITE_API_BASE` to point at a deployed API instead of the dev proxy.

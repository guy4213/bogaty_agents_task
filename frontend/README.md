# Content Engine Frontend

Minimal testing UI for the Content Engine backend. Built with Next.js 14, TypeScript, Tailwind CSS, and TanStack Query v5.

## Setup

```bash
cd frontend
npm install
cp .env.local.example .env.local
# Edit .env.local if the backend runs on a different port
npm run dev
```

The app starts at [http://localhost:3000](http://localhost:3000).  
The backend must be running at `http://localhost:8000` (or the URL set in `.env.local`).

## Scripts

```bash
npm run dev        # start dev server on port 3000
npm run build      # production build
npm run start      # serve production build
npm run typecheck  # TypeScript type check (no emit)
npm run lint       # ESLint check
```

## Key pages

| Path | Description |
|---|---|
| `/` | New Task form |
| `/tasks/[taskId]` | Task detail — pipeline status, metrics, and result gallery |

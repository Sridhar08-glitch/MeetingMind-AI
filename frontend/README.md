<div align="center">

# 🖥️ MeetingMind AI — Frontend

**Next.js 16 · React 19 · TypeScript · Tailwind CSS 4 · TanStack Query · Zustand**

[![Next.js](https://img.shields.io/badge/Next.js-16-000000?style=flat-square&logo=nextdotjs&logoColor=white)](https://nextjs.org/)
[![React](https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?style=flat-square&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Tailwind](https://img.shields.io/badge/Tailwind-4-06B6D4?style=flat-square&logo=tailwindcss&logoColor=white)](https://tailwindcss.com/)
[![React Query](https://img.shields.io/badge/TanStack%20Query-5-FF4154?style=flat-square&logo=reactquery&logoColor=white)](https://tanstack.com/query)

</div>

The MeetingMind frontend is a **Next.js 16 (App Router)** application in TypeScript. It consumes the backend REST API through typed clients, manages server state with **TanStack Query** and UI state with **Zustand**, and is styled with **Tailwind CSS 4** design tokens (with a no-flash dark mode).

> 📚 See the root [README](../README.md) for the product overview.

---

## 🧭 App Router

Routes live under `src/app/`, using route groups:

- `(auth)` → login, register, forgot/reset password
- `(dashboard)` → the authenticated app shell (sidebar, topbar, command palette, guards)

The dashboard layout mounts global pieces once: command palette (⌘K), global search (`/`), toasts, keyboard-shortcut help, document title, and the processing-toast watcher.

---

## 🗂️ Structure

```
frontend/
├── src/
│   ├── app/
│   │   ├── (auth)/                 # login / register / reset
│   │   └── (dashboard)/            # authenticated app
│   │       ├── copilot/            # AI workspace home (primary entry)
│   │       ├── meetings/           # list, upload, detail (transcript/AI/chat)
│   │       ├── workspace/          # Kanban, AI approvals
│   │       ├── knowledge/          # org search, chat, graph, timeline
│   │       ├── executive/          # health, analytics, alerts, brief
│   │       ├── agents/             # agent center, planner, collaboration
│   │       ├── people/             # cross-meeting voice identities
│   │       └── settings/           # appearance, preferences, system
│   ├── components/                 # UI, panels, graphs, layout, copilot
│   ├── lib/api/                    # typed API clients (unwrap {success,data})
│   ├── hooks/                      # React Query hooks
│   ├── store/                      # Zustand stores (theme, toast, recents…)
│   └── types.ts                    # shared TypeScript types
└── package.json
```

---

## 🔌 API Layer

`src/lib/api/` holds one typed client per domain (`meetings`, `workspace`, `knowledge`, `executive`, `agents`, `people`, …). A shared axios instance attaches the JWT and an `unwrap()` helper unpacks the backend's `{ success, data }` envelope.

```ts
// Example: fetch a meeting's AI analysis
const { data } = await api.get<ApiSuccess<AIAnalysis>>(`/meetings/${id}/ai/`);
return data.data;
```

---

## 🔄 State Management

| Concern | Tool | Notes |
|---------|------|-------|
| **Server state** | TanStack Query 5 | Caching, polling (during processing), invalidation |
| **Client/UI state** | Zustand 5 | Theme, toasts, recents, pinned widgets, preferences (persisted) |
| **Forms** | react-hook-form + zod | Typed validation |

---

## 🎨 Theming & UI

- **Tailwind CSS 4** with CSS design tokens (`--color-surface / foreground / brand-* …`); a `.dark {}` token override themes the entire app.
- No-flash dark mode via a render-blocking theme script; supports light / dark / system.
- Accessible primitives: focus-trapped dialogs, skip-to-content, `aria-*`, `prefers-reduced-motion`.
- Icons from `lucide-react`; charts and graphs are hand-rolled SVG.

---

## 🔐 Authentication

JWT-based. On login the access token is stored client-side and attached to every request; a client-side guard in the `(dashboard)` layout redirects unauthenticated users to `/login?next=…`.

---

## 🚀 Getting Started

```bash
npm install

# Point at your backend
echo "NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000/api" > .env.local

npm run dev        # dev server at http://localhost:3000
```

### Production build

```bash
npm run build
npx next start -p 3000
```

### Quality gates

```bash
npx tsc --noEmit   # type-check
npx eslint src     # lint
```

> ℹ️ This project targets **Next.js 16 / React 19** — some APIs differ from older majors. Prefer a production build (`next build` + `next start`) when verifying behavior in the browser.

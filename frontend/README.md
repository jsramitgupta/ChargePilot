# ChargePilot frontend

The browser UI is a React 19 and TypeScript single-page application built with
Vite and Tailwind CSS. `src/App.tsx` owns the React Router routes, session-aware
navigation, and page workflows. The frontend calls the FastAPI JSON API and
uses the authenticated browser session; FastAPI remains responsible for
authorization, tenant isolation, battery rules, and device operations.

## Design references

The canonical route inventory, visual decisions, typography guidance, theme
behavior, and UI change checklist are in
[`.github/instructions/FRONTEND_DESIGN.md`](../.github/instructions/FRONTEND_DESIGN.md).
The short project-wide status is in
[`.github/instructions/CURRENT_STATE.md`](../.github/instructions/CURRENT_STATE.md).

Shared light-theme tokens, layout, and components are in `src/index.css`.
`src/theme.css` defines dark-theme tokens and focused dark-mode adjustments.
Keep both themes aligned when changing a shared component, including its
interactive and status states.

## Development

Install dependencies with `npm ci`, then run the frontend from this directory:

```sh
npm run dev
npm run lint
npm run build
```

`npm run build` runs the TypeScript project build before creating the Vite
production bundle. The backend serves the built application and provides
runtime API/frontend origins; do not hardcode deployment URLs or credentials
in frontend source.

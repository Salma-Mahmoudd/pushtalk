# PushTalk web

The PushTalk browser app: React + TypeScript, built with Vite.

## Scripts

Run from `apps/web/` (Node and pnpm versions: see [`../../steps/environment-setup.md`](../../steps/environment-setup.md)).

| Command | What it does |
| --- | --- |
| `pnpm install` | Install dependencies from `pnpm-lock.yaml` |
| `pnpm dev` | Development server with hot reload on <http://localhost:5173> |
| `pnpm build` | Type-check and build optimised static files into `dist/` |
| `pnpm preview` | Serve the built `dist/` locally to check a production build |
| `pnpm lint` | ESLint |

In Docker, the `web` image builds the app and nginx serves `dist/`.

## Configuration

| Variable | Default | Used for |
| --- | --- | --- |
| `VITE_SITE_URL` | `http://localhost:8080` | Absolute address in the social-preview tags (`og:url`, `og:image`) of `index.html` |

## Brand assets

| File | Purpose |
| --- | --- |
| `brand/mark.svg` | Master logo: speech bubble with voice waveform on Twitter blue `#1e9df1` |
| `brand/logo-light.svg`, `brand/logo-dark.svg` | Logo + "PushTalk" wordmark for light and dark backgrounds (used by the project README) |
| `public/favicon.svg`, `public/favicon.ico` | Browser tab icon (SVG for current browsers, ICO with 16/32/48 px) |
| `public/apple-touch-icon.png` | Icon for Safari bookmarks and the iOS home screen (180 px) |
| `public/og-image.png` | Link preview image (1200 × 630) for Open Graph and Twitter cards |

## Metadata

`index.html` holds the page title, description, light/dark theme colors, icons, and Open Graph / Twitter card tags. `public/robots.txt` allows indexing of the sign-in pages only; channels and the API require an account.

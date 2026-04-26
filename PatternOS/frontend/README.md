# PatternOS frontend (Next.js)

## Development (hot reload — higher CPU)

From this `frontend` folder:

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). Use this when **changing UI code** day to day.

## Production (recommended on a server — lower CPU)

**Always** use a production build for anything users hit on a VPS or the public internet. `next dev` keeps compilers and watchers running and uses much more CPU and RAM.

From this `frontend` folder:

```bash
npm install
npm run build
npm run start
```

Or one command:

```bash
npm run prod
```

**Port:** set the `PORT` environment variable (default is `3000`). Example:

```bash
PORT=3001 npm run prod
```

**API base URL:** set `NEXT_PUBLIC_API_BASE_URL` in `.env` (or in the shell) so the browser calls your FastAPI backend (e.g. `https://your-api.example.com/api/v1`).

### From the PatternOS repo root (Linux/macOS)

```bash
./scripts/run-frontend-prod.sh
```

### From the PatternOS repo root (Windows)

Double-click or run:

```bat
start-frontend-prod.bat
```

---

This project uses [Next.js](https://nextjs.org). For framework docs, see [Next.js Documentation](https://nextjs.org/docs).

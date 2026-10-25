# Runbook: starting and stopping Wally

Commands for Windows **PowerShell**. Project folder:

```
C:\Users\adhiy\Downloads\Wally-master\Wally-master
```

Wally needs three things running, each in its own terminal window:

| # | Service | Port | Check it at |
|---|---|---|---|
| 1 | Qdrant (vector database, in Docker) | 6333 | <http://localhost:6333/dashboard> |
| 2 | Backend (FastAPI) | 8001 | <http://localhost:8001/health> |
| 3 | Frontend (Next.js) | 3000 | <http://localhost:3000> |

---

## Start everything

### 1. Docker and Qdrant

Open **Docker Desktop** from the Start menu and wait until it says *Engine running*. Then, in a terminal:

```powershell
docker start eager_leavitt
```

Check: open <http://localhost:6333/dashboard>. You should see the `docs` collection.

### 2. Backend (terminal 2)

```powershell
cd C:\Users\adhiy\Downloads\Wally-master\Wally-master
.\venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8001
```

Wait for `Application startup complete.` Leave this window open.
Check: <http://localhost:8001/health> shows `"status":"healthy"`.

### 3. Frontend (terminal 3)

```powershell
cd C:\Users\adhiy\Downloads\Wally-master\Wally-master\wally-frontend
npm run dev
```

Wait for `Ready`. Leave this window open.
Open <http://localhost:3000>. The sidebar foot should read **Online**.

---

## Stop everything

1. In the frontend and backend windows, press **Ctrl + C** (press it twice if asked), then close them.
2. Stop Qdrant:
   ```powershell
   docker stop eager_leavitt
   ```
3. Quit Docker Desktop if you want (tray icon → Quit).

Your uploaded documents stay inside the `eager_leavitt` container and come back after `docker start eager_leavitt`.

> **Don't delete the container** (`docker rm eager_leavitt`, or the bin icon in Docker Desktop). It has no separate storage volume, so deleting it deletes the indexed documents. If that happens, see *Recreate Qdrant* below and re-upload the files.

---

## Before a demo

1. Start all three services (above).
2. Open <http://localhost:3000> in a maximised window.
3. **Settings** → turn **Rerank passages** on (loads the model once).
4. Follow [DEMO_GUIDE.md](DEMO_GUIDE.md). The demo files are in the `demo` folder.

---

## Common problems

| Problem | Fix |
|---|---|
| `docker` not recognised, or "cannot connect to the Docker daemon" | Docker Desktop isn't running. Start it and wait for *Engine running*. |
| Sidebar says **API offline** | The backend window was closed or crashed. Restart step 2. |
| Sidebar says **Database offline** | `docker start eager_leavitt` |
| "Address already in use" / port 8001 or 3000 busy | Find and stop the old process (below). |
| Backend error `GROQ_API_KEY not set` | `.env` is missing from the project folder. Create it from `.env.example` and add your key. |
| Frontend shows an old version | Stop it with Ctrl + C and run `npm run dev` again; refresh the browser with Ctrl + F5. |
| Groq tokens per minute not shown | Maximise the window and ask one question; the number comes from Groq's reply. |

**Free a busy port** (replace 8001 with 3000 for the frontend):

```powershell
netstat -ano | findstr :8001
taskkill /PID <number from the last column> /F
```

---

## Start fresh (empty library)

With everything running:

1. **Library** → **Remove** each document.
2. Delete the knowledge gaps and feedback:
   ```powershell
   Remove-Item C:\Users\adhiy\Downloads\Wally-master\Wally-master\wally_data\insights.json
   ```
3. Restart the backend (Ctrl + C, then step 2 again). This also resets the Performance numbers.

---

## Recreate Qdrant (only if the container was deleted)

This version keeps data in a named volume, so it survives even if the container is deleted later:

```powershell
docker run -d --name wally-qdrant -p 6333:6333 -p 6334:6334 -v wally_qdrant:/qdrant/storage qdrant/qdrant
```

From then on, use `docker start wally-qdrant` / `docker stop wally-qdrant` instead of `eager_leavitt`. Re-upload your documents in the Library.

---

## Set up on a new computer

Needs Python 3.12, Node.js 20+, Git and Docker Desktop.

```powershell
git clone https://github.com/ichor-hash/Wally.git
cd Wally

# Vector database
docker run -d --name wally-qdrant -p 6333:6333 -p 6334:6334 -v wally_qdrant:/qdrant/storage qdrant/qdrant

# Backend
py -3.12 -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
notepad .env        # paste your GROQ_API_KEY; set COMPANY_NAME / COMPANY_PROFILE for the Apple demo

# Frontend
cd wally-frontend
npm install
cd ..
```

Then follow *Start everything* (using `wally-qdrant` instead of `eager_leavitt`). The first backend start downloads the embedding model (about 90 MB).

---

## Save and publish changes

```powershell
cd C:\Users\adhiy\Downloads\Wally-master\Wally-master
git status                      # see what changed
git add -A
git commit -m "Describe the change"
git push
```

Get the latest version from GitHub: `git pull`.

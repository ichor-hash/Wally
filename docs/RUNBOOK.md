# Runbook: starting and stopping Ethan

Commands for Windows **PowerShell**. Project folder:

```
C:\Users\adhiy\Downloads\Wally-master\Wally-master
```

Ethan needs two things running, each in its own terminal window. **Docker is not needed**: the vector database (Qdrant) runs inside the backend and keeps its data in `ethan_data\qdrant`.

| # | Service | Port | Check it at |
|---|---|---|---|
| 1 | Backend (FastAPI, with embedded Qdrant) | 8001 | <http://localhost:8001/health> |
| 2 | Frontend (Next.js) | 3000 | <http://localhost:3000> |

This relies on `QDRANT_PATH=./ethan_data/qdrant` in `.env`. Without that line the backend looks for a Qdrant server on port 6333 instead; see [Using the Docker Qdrant instead](#using-the-docker-qdrant-instead).

---

## Start everything

### 1. Backend (terminal 1)

```powershell
cd C:\Users\adhiy\Downloads\Wally-master\Wally-master
.\venv\Scripts\python.exe -m uvicorn main:app --port 8001
```

Wait for `Application startup complete.` Leave this window open.
Check: <http://localhost:8001/health> shows `"status":"healthy"`.

### 2. Frontend (terminal 2)

```powershell
cd C:\Users\adhiy\Downloads\Wally-master\Wally-master\ethan-frontend
npm run dev
```

Wait for `Ready`. Leave this window open.
Open <http://localhost:3000>. The sidebar foot should read **Online**.

The first time, open **Library** and drag in the files from the `demo` folder.

---

## Stop everything

In both windows press **Ctrl + C** (twice if asked), then close them. Uploaded documents stay in `ethan_data\qdrant` and are there next time.

> Only one backend can use the embedded database at a time. If a second one starts, it fails with a "storage folder is already accessed" error: close the other window first.

---

## Before a demo

1. Start both services (above).
2. Open <http://localhost:3000> in a maximised window.
3. Rerank is on by default and loads in the background when the page opens. Charts are off by default: turn on **Settings → Charts and tables** if you want to show them.
4. Follow [DEMO_GUIDE.md](DEMO_GUIDE.md).

---

## Checks

```powershell
cd C:\Users\adhiy\Downloads\Wally-master\Wally-master
.\venv\Scripts\python.exe -m pytest -q tests          # unit tests, a few seconds
.\venv\Scripts\python.exe evals\run_evals.py          # retrieval evaluation, about a minute
.\venv\Scripts\python.exe evals\run_evals.py --answers   # also grade answers (uses Groq tokens)

cd ethan-frontend
npm run lint; npm run typecheck
npm run gen:prompt     # after changing lib\visuals-library.ts or upgrading @openuidev packages
```

The evaluation writes `evals\results\REPORT.md`, which the **Evaluation** page shows.

---

## Common problems

| Problem | Fix |
|---|---|
| Sidebar says **API offline** | The backend window was closed or crashed. Restart step 1. |
| Sidebar says **Database offline** | Another backend holds the embedded database, or `QDRANT_PATH` points at a missing folder. Close other backend windows and restart. |
| Backend error "storage folder ... is already accessed by another instance" | A second backend is running. Free port 8001 (below) and start one. |
| Settings shows **Language model: Not configured** | `.env` has no `GROQ_API_KEY`, or `LLM_PROVIDER` points at a local server that isn't running. |
| "Address already in use", port 8001 or 3000 busy | Find and stop the old process (below). |
| Library is empty after upgrading | Version 3 uses a new collection, `ethan_docs`. Re-upload the files, or migrate (below). |
| Frontend shows an old version | Ctrl + C, `npm run dev` again, then refresh with Ctrl + F5. |
| Charts setting says *Unavailable* | `prompts\openui.txt` is missing. Run `npm run gen:prompt` in `ethan-frontend`, then restart the backend. |

**Free a busy port** (replace 8001 with 3000 for the frontend):

```powershell
netstat -ano | findstr :8001
taskkill /PID <number from the last column> /F
```

---

## Start fresh (empty library)

1. **Library** → **Remove** each document.
2. Stop the backend, then delete the knowledge gaps, feedback, cost totals and query history:
   ```powershell
   Remove-Item C:\Users\adhiy\Downloads\Wally-master\Wally-master\ethan_data\insights.json, C:\Users\adhiy\Downloads\Wally-master\Wally-master\ethan_data\queries.jsonl
   ```
3. Start the backend again.

---

## Using the Docker Qdrant instead

Your older documents are in the Docker container `eager_leavitt`, in the collection `docs`. To use them:

1. Start **Docker Desktop**, then run `docker start eager_leavitt`.
2. In `.env`, delete the `QDRANT_PATH=...` line, so the backend uses `http://localhost:6333`.
3. Copy the old chunks into a hybrid-search collection once:
   ```powershell
   .\venv\Scripts\python.exe scripts\migrate_collection.py --source docs --target ethan_docs
   ```
4. Restart the backend.

Don't delete that container: it has no separate storage volume, so deleting it deletes its documents.

---

## Set up on a new computer

Needs Python 3.12, Node.js 20+ and Git. Docker is optional.

```powershell
git clone https://github.com/ichor-hash/Wally.git ethan
cd ethan

# Backend (CPU build of PyTorch first: much smaller)
py -3.12 -m venv venv
.\venv\Scripts\python.exe -m pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu
.\venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
notepad .env        # paste your GROQ_API_KEY; set COMPANY_NAME / COMPANY_PROFILE for the Apple demo

# Frontend
cd ethan-frontend
npm install
cd ..
```

Then follow *Start everything*. The first backend start downloads the embedding model and reranker (about 175 MB).

---

## Save and publish changes

```powershell
cd C:\Users\adhiy\Downloads\Wally-master\Wally-master
git status                      # see what changed
git add -A
git commit -m "Describe the change"
git push
```

Every push runs CI on GitHub (tests, the evaluation gate, frontend checks): see the **Actions** tab. Get the latest version: `git pull`.

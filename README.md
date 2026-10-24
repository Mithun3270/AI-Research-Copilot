# AI Research Copilot

## 1. Project overview

AI Research Copilot indexes research PDFs with all-MiniLM-L6-v2 embeddings and FAISS.
It uses a local FastAPI API, a React and Vite interface, and Ollama with qwen2.5:3b.
Expected result: seven reproducibly seeded papers, 173 FAISS vectors, stable categories, cited chat answers, and per-paper analysis.

## 2. Prerequisites

Install these Windows versions before continuing. The download links are official sources.

| Tool | Version used for this project | Download |
|---|---:|---|
| Python | 3.14.0 | [Python 3.14.0 for Windows](https://www.python.org/downloads/release/python-3140/) |
| Node.js | 24.11.1, including npm 11.6.2 | [Node.js 24.11.1 archive](https://nodejs.org/en/download/archive/v24.11.1/) |
| Git for Windows | 2.51.2.windows.1 | [Git for Windows 2.51.2 release](https://github.com/git-for-windows/git/releases/tag/v2.51.2.windows.1) |
| Ollama | 0.40.10 | [Ollama for Windows](https://ollama.com/download/windows) |

To install the exact Ollama version listed above, run this in PowerShell:

```powershell
$env:OLLAMA_VERSION = "0.40.10"
irm https://ollama.com/install.ps1 | iex
Remove-Item Env:OLLAMA_VERSION
```

Verify the installed versions in PowerShell:

```powershell
py -3.14 --version
node --version
npm --version
git --version
ollama --version
```

The expected output is Python 3.14.0, Node v24.11.1, npm 11.6.2, Git 2.51.2.windows.1, and Ollama 0.40.10.

## 3. Clone the project

1. Clone the repository and enter its folder:

```powershell
git clone https://github.com/Mithun3270/AI-Research-Copilot.git
Set-Location AI-Research-Copilot
```

2. The files needed for setup and seeding are arranged like this:

```text
AI-Research-Copilot/
├── backend/
│   ├── app.py
│   ├── config.py
│   ├── requirements.txt
│   ├── research_copilot.py
│   └── seed.py
├── frontend/
│   ├── src/
│   └── package.json
├── model/embedding_model/
├── sample_papers/
├── scripts/
├── .env.example
├── package.json
└── seed_manifest.json
```

The `sample_papers` folder contains the seven PDFs used for the reproducible seed. The local embedding model is included in `model/embedding_model`; the FAISS index, SQLite database, extracted text, and generated reports are created locally.

## 4. First-time setup

Run these commands from the project root in Windows PowerShell:

1. Create the virtual environment with Python 3.14:

```powershell
py -3.14 -m venv .venv
```

2. Install the pinned backend dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip==26.2.2
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

3. Install the pinned root and frontend Node.js dependencies:

```powershell
npm ci
npm ci --prefix frontend
```

4. Create the local environment file from the checked-in defaults:

```powershell
Copy-Item .env.example .env
```

5. Download the required Ollama model:

```powershell
ollama pull qwen2.5:3b
```

6. Index the seven sample PDFs:

```powershell
npm run seed
```

The seed command creates or refreshes the seven sample papers, uses their checked-in category mapping for stable category names, updates the SQLite metadata, and rebuilds the FAISS index. It checks for exactly 173 vectors and the expected category counts. It refuses to run if unrelated papers are already indexed; export or remove those papers before seeding.

7. The setup script is also available when you want dependency installation and environment-file creation automated:

```powershell
npm run setup
```

It uses the lockfiles, creates `.venv` with Python 3.14 when needed, installs the pinned backend packages, and copies `.env.example` to `.env` only if `.env` does not already exist. Run the Ollama model download and seed commands from steps 5 and 6 after it completes.

## 5. Daily run

1. Open one terminal at the project root and run:

```powershell
npm run dev
```

2. The command starts Ollama if needed, checks for qwen2.5:3b, starts FastAPI and Vite, waits for both web services, prints their links, and opens the frontend in the default browser. All process output stays in this terminal.

3. Verify the application links:

```text
Frontend: http://127.0.0.1:5173
Backend:  http://127.0.0.1:8000
API docs: http://127.0.0.1:8000/docs
```

4. Press Ctrl+C in the terminal to stop the processes. To stop project-managed processes from another terminal, run:

```powershell
npm run stop
```

An Ollama process that was already running before startup is not stopped by the project.

## 6. Expected output checklist

After seeding and starting the app, confirm each item:

1. The header reports all-MiniLM-L6 with 384 dimensions, FAISS with 173 vectors, and qwen2.5:3b online.
2. Paper Repository shows seven PDFs.
3. The sidebar categories and paper counts are:
   - Environment: 4 papers
   - Mobile Edge Computing: 1 paper
   - Neuroprosthetics: 1 paper
   - Robotics And Rehabilitation: 1 paper
4. Research Chat searches across the indexed papers, provides paper and page citations for supported questions, and returns “Not found in your indexed papers” for unsupported questions.
5. Paper Analysis can analyze one selected paper, show its structured report and paper-derived architecture figure or diagram, and download the report as a PDF.
6. The API health page at `http://127.0.0.1:8000/health` reports seven papers and 173 synchronized vectors.

## 7. Sample test inputs

Use the same inputs to compare behavior after seeding:

1. In Research Chat, ask:

```text
What is ChatGPT?
```

This topic is not present in the seeded papers, so the expected answer is “Not found in your indexed papers.”

2. In Research Chat, ask:

```text
What gait parameters does the SoleSound system measure?
```

The answer should be grounded in the indexed gait paper and include at least one paper name and page citation.

3. In Paper Analysis, select:

```text
AIoT-Based_Digital_Monitoring_Architectures_for_Wa.pdf
```

Then click “Run Deep Analysis.” The seeded copy contains an original architecture/system overview figure on page 6, which should be shown with its page label.

## 8. Troubleshooting

1. If ports 8000, 5173, or 11434 are already in use, stop the process using that port or close the other application, then retry the daily startup step. The project skips starting a second Ollama server if port 11434 is already occupied.
2. If Ollama is not running, start the Ollama desktop application, then retry the daily startup step. The project normally starts Ollama when the port is free.
3. If qwen2.5:3b is missing, run:

```powershell
ollama pull qwen2.5:3b
```

4. If PowerShell blocks `npm.ps1`, use the Windows command shim:

```powershell
npm.cmd run dev
```

5. If Python or Node.js is missing or the version is wrong, install the versions in step 2, reopen PowerShell, and verify the commands in step 2 before running setup.
6. If FAISS installation fails, confirm Python 3.14 is active and recreate the virtual environment:

```powershell
Remove-Item -Recurse -Force .venv
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip==26.2.2
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

7. If the seed reports missing PDFs, confirm that all seven files are present in `sample_papers` and rerun the seed step from first-time setup. If it reports unrelated indexed papers, do not delete them blindly; back them up before clearing generated index/database files and seeding again.
8. If the model or FAISS files are missing after cloning, run the first-time setup steps again. The embedding model and sample PDFs are repository inputs; the database and vector index are generated by the seed.

## 9. Reproducibility notes

1. The sample PDFs, embedding model, category mapping, Python dependency versions, npm package versions, and package lockfiles are pinned or checked in. The seed validates the PDF and embedding-model SHA-256 checksums, so a clean clone produces the same paper set, categories, 173-vector count, and paper/page citation sources.
2. LLM wording can differ slightly because qwen2.5:3b generates text. The papers, categories, vector count, and retrieved citation sources should still match.
3. The root `.env.example` contains working local defaults. Email settings are optional and are not needed for paper indexing, chat, or analysis.
4. The embedding model file is about 90.9 MB. GitHub accepts it below the 100 MB per-file limit, but shows a large-file warning; include it in the push or the seed cannot verify and use the checked-in model.

## 10. API reference

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | Report FAISS, embedding model, paper, and Ollama status |
| `GET` | `/papers` | List indexed papers, categories, chunk counts, and pages |
| `PATCH` | `/papers/{paper_name}/category` | Change a paper category |
| `POST` | `/upload` | Extract and index a research PDF |
| `DELETE` | `/papers/{paper_name}` | Remove a paper and rebuild FAISS |
| `GET` | `/paper-file/{paper_name}` | Serve a paper PDF |
| `POST` | `/search` | Search indexed paper chunks |
| `POST` | `/ask` | Ask a grounded question with page citations |
| `POST` | `/analyze` | Generate a report for one paper |
| `POST` | `/analysis/architecture` | Retry architecture diagram generation |
| `POST` | `/analysis/pdf` | Download a paper analysis report |
| `POST` | `/compare` | Compare two or more papers |
| `POST` | `/research-gap` | Analyze research gaps for one paper |
| `POST` | `/literature-review` | Generate a literature review |
| `POST` | `/citation` | Generate an academic citation |
| `GET` | `/outputs` | List generated reports |
| `GET` | `/outputs/{filename}` | Download a generated report |

## 11. Configuration

Copy `.env.example` to `.env` to customize the local settings. Defaults are:

| Variable | Default |
|---|---|
| `DATABASE_URL` | `sqlite:///data/research_copilot.db` |
| `OLLAMA_URL` | `http://127.0.0.1:11434` |
| `OLLAMA_MODEL` | `qwen2.5:3b` |
| `CATEGORY_SIMILARITY_THRESHOLD` | `0.55` |
| `RAG_MIN_COSINE_SIMILARITY` | `0.30` |
| `FRONTEND_URL` | `http://127.0.0.1:5173` |

Categories for newly uploaded papers are classified from the paper text and updated using paper embeddings and category centroids. A category is proposed by Ollama when no existing centroid meets the configured similarity threshold.

## 12. Main features

1. Research Chat answers from the indexed library and cites paper names and page numbers.
2. Paper Analysis creates a structured, single-paper report and displays an original PDF figure or a paper-grounded generated architecture diagram.
3. Research Gap analysis is scoped to one selected paper.
4. The paper repository supports PDF upload, category filtering, category overrides, and deletion.
5. Paper comparison, literature review, and citation generation are also available.
6. The application runs locally with FastAPI, React, Vite, FAISS, Sentence Transformers, and Ollama.

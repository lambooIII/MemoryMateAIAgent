$ErrorActionPreference = 'Stop'

conda run --no-capture-output -n langchain1.2 `
    python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload


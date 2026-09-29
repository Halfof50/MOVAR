from fastapi import FastAPI

app = FastAPI(title="MOVAR AI")

@app.get("/health")
def health():
    return {"status": "ok"}
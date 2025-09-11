from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root():
    return {"hello": "hotel"}
@app.get("/health")
def health():
    return {"status": "ok"}

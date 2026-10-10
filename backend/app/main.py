from fastapi import FastAPI

app = FastAPI(title="Chess Opening Coach API")


@app.get("/")
def hello():
    return {"message": "Hello World"}


@app.get("/health")
def health():
    return {"status": "ok"}

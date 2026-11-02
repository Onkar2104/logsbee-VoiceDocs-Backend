from fastapi import FastAPI

app = FastAPI(title="My FastAPI Project")


@app.get("/health")
def home():
    return {"message": "FastAPI project started successfully"}
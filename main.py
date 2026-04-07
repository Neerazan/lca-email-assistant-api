from fastapi import FastAPI

app = FastAPI(title="LCA Email Assistant")

@app.get("/")
def read_root():
    return {"message": "Hello from LCA Email Assistant!"}

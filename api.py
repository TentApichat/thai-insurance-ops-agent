"""REST API so other systems (an email server, a core insurance system) can call the agent.

Run:  uvicorn api:app --reload
Docs: http://127.0.0.1:8000/docs
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agent.graph import build_graph
from agent.llm import get_extractor
from agent.store import RequestStore

store = RequestStore()
extractor = get_extractor()
graph = build_graph(extractor, store)

app = FastAPI(
    title="Thai Insurance Ops Agent",
    description="Triage broker emails into endorsements, claims, pre-inspections and quotes, with a human in the loop.",
)


class TriageRequest(BaseModel):
    text: str


class Decision(BaseModel):
    reviewer: str
    approve: bool
    note: str = ""


@app.post("/triage")
def triage(body: TriageRequest) -> dict:
    result = graph.invoke({"text": body.text})
    return {key: result[key] for key in ("record_id", "route", "team", "extraction", "issues")}


@app.get("/review-queue")
def review_queue() -> list[dict]:
    return store.review_queue()


@app.post("/requests/{request_id}/decision")
def decide(request_id: int, body: Decision) -> dict:
    try:
        return store.decide(request_id, body.reviewer, body.approve, body.note)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error))
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error))


@app.get("/requests/{request_id}/history")
def history(request_id: int) -> list[dict]:
    if store.get(request_id) is None:
        raise HTTPException(status_code=404, detail=f"No request with id {request_id}")
    return store.history(request_id)

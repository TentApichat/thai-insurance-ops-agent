"""The LangGraph workflow: extract -> validate -> (auto route | human review) -> save."""

from __future__ import annotations

from datetime import date
from typing import Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from .llm import Extractor, clean_extraction, get_extractor
from .schema import Extraction, RequestType
from .store import RequestStore
from .validators import TEAMS, validate


class TriageState(TypedDict, total=False):
    text: str
    today: str          # optional ISO date, so evaluations are reproducible
    extraction: dict
    issues: list[str]
    route: str          # "auto" or "human_review"
    team: str
    record_id: int


def build_graph(extractor: Optional[Extractor] = None, store: Optional[RequestStore] = None):
    extractor = extractor or get_extractor()
    store = store or RequestStore()

    def today_of(state: TriageState) -> date:
        return date.fromisoformat(state["today"]) if state.get("today") else date.today()

    def extract_node(state: TriageState) -> TriageState:
        extraction = clean_extraction(extractor.extract(state["text"], today_of(state)))
        return {"extraction": extraction.model_dump(mode="json")}

    def validate_node(state: TriageState) -> TriageState:
        extraction = Extraction.model_validate(state["extraction"])
        return {"issues": validate(extraction, state["text"], today_of(state))}

    def choose_route(state: TriageState) -> str:
        return "human_review" if state["issues"] else "auto_route"

    def auto_route_node(state: TriageState) -> TriageState:
        request_type = RequestType(state["extraction"]["request_type"])
        return {"route": "auto", "team": TEAMS[request_type]}

    def human_review_node(state: TriageState) -> TriageState:
        request_type = RequestType(state["extraction"]["request_type"])
        return {"route": "human_review", "team": TEAMS[request_type]}

    def save_node(state: TriageState) -> TriageState:
        record_id = store.save(
            text=state["text"],
            extraction=state["extraction"],
            issues=state["issues"],
            route=state["route"],
            team=state["team"],
            extractor=extractor.name,
        )
        return {"record_id": record_id}

    graph = StateGraph(TriageState)
    graph.add_node("extract", extract_node)
    graph.add_node("validate", validate_node)
    graph.add_node("auto_route", auto_route_node)
    graph.add_node("human_review", human_review_node)
    graph.add_node("save", save_node)

    graph.add_edge(START, "extract")
    graph.add_edge("extract", "validate")
    graph.add_conditional_edges(
        "validate", choose_route, {"auto_route": "auto_route", "human_review": "human_review"}
    )
    graph.add_edge("auto_route", "save")
    graph.add_edge("human_review", "save")
    graph.add_edge("save", END)
    return graph.compile()

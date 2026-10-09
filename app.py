"""Web demo: paste a broker email, see how the agent routes it, then work the review queue.

Run:  python app.py   (then open the local link it prints)
"""

import json
from pathlib import Path

import gradio as gr

from agent.graph import build_graph
from agent.llm import get_extractor
from agent.store import RequestStore

SAMPLES = [
    json.loads(line)["text"]
    for line in (Path(__file__).parent / "data" / "sample_requests.jsonl").read_text(encoding="utf-8").splitlines()
    if line.strip()
]

store = RequestStore()
extractor = get_extractor()
graph = build_graph(extractor, store)


def run_triage(text: str):
    if not text.strip():
        return "Paste an email first.", {}, ""
    result = graph.invoke({"text": text})
    if result["route"] == "auto":
        headline = f"### Routed automatically to **{result['team']}** (request #{result['record_id']})"
        issues = "No issues found."
    else:
        headline = f"### Sent to the human review queue (request #{result['record_id']}, suggested team: {result['team']})"
        issues = "\n".join(f"- {issue}" for issue in result["issues"])
    return headline, result["extraction"], issues


def queue_rows():
    return [
        [r["id"], r["request_type"], round(r["confidence"], 2), "; ".join(r["issues"]), r["text"][:90]]
        for r in store.review_queue()
    ]


def record_decision(request_id, reviewer: str, approve: bool):
    if request_id is None or not reviewer.strip():
        return "Enter a request number and your name.", queue_rows()
    try:
        store.decide(int(request_id), reviewer.strip(), approve)
    except (KeyError, ValueError) as error:
        return str(error), queue_rows()
    verb = "approved" if approve else "rejected"
    return f"Request #{int(request_id)} {verb} by {reviewer.strip()}. Logged in the audit trail.", queue_rows()


with gr.Blocks(title="Thai Insurance Ops Agent") as demo:
    gr.Markdown(
        "# Thai Insurance Ops Agent\n"
        "Triage broker emails in Thai or English into endorsements, claims, pre-inspections and quotes. "
        f"Clear requests go straight to a team; anything risky waits for a person. Extractor: **{extractor.name}**."
    )
    with gr.Tab("Triage"):
        sample = gr.Dropdown(choices=SAMPLES, label="Try a sample email", value=None)
        email = gr.Textbox(lines=7, label="Broker email")
        sample.change(lambda s: s, inputs=sample, outputs=email)
        run = gr.Button("Triage", variant="primary")
        headline = gr.Markdown()
        with gr.Row():
            extraction = gr.JSON(label="Extracted fields")
            issues = gr.Markdown(label="Why it needs review")
        run.click(run_triage, inputs=email, outputs=[headline, extraction, issues])

    with gr.Tab("Review queue"):
        table = gr.Dataframe(
            headers=["#", "Type", "Confidence", "Issues", "Email"],
            value=queue_rows,
            interactive=False,
            wrap=True,
        )
        refresh = gr.Button("Refresh queue")
        with gr.Row():
            request_id = gr.Number(label="Request #", precision=0)
            reviewer = gr.Textbox(label="Your name")
        with gr.Row():
            approve = gr.Button("Approve", variant="primary")
            reject = gr.Button("Reject", variant="stop")
        status = gr.Markdown()
        refresh.click(queue_rows, outputs=table)
        approve.click(lambda i, r: record_decision(i, r, True), inputs=[request_id, reviewer], outputs=[status, table])
        reject.click(lambda i, r: record_decision(i, r, False), inputs=[request_id, reviewer], outputs=[status, table])


if __name__ == "__main__":
    demo.launch()

import os
import json
import queue
import uuid
import threading
from pathlib import Path
from flask import Flask, render_template, request, jsonify, Response
from dotenv import load_dotenv
from agent.policy_extractor import PolicyExtractor

load_dotenv()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB

POLICIES_DIR = Path("policies")
POLICIES_DIR.mkdir(exist_ok=True)

# session_id -> Queue of SSE event dicts
_sse_queues: dict[str, queue.Queue] = {}
_sse_lock = threading.Lock()


def _get_queue(session_id: str) -> queue.Queue:
    with _sse_lock:
        if session_id not in _sse_queues:
            _sse_queues[session_id] = queue.Queue()
        return _sse_queues[session_id]


def _push(session_id: str, event: dict):
    _get_queue(session_id).put(event)


def _run_extraction(session_id: str, filepath: str):
    extractor = PolicyExtractor()
    try:
        _push(session_id, {"type": "status", "phase": "reading", "message": "Reading PDF document..."})

        _push(session_id, {"type": "status", "phase": "extracting", "message": "Sending to Claude AI for analysis..."})

        policy_data = extractor.extract(filepath)

        _push(session_id, {"type": "status", "phase": "populating", "message": "Populating AMS fields..."})

        # Stream fields one by one so the UI can animate them
        field_order = [
            # Policy section
            ("policy", "policy_number", "Policy Number"),
            ("policy", "carrier", "Insurance Carrier"),
            ("policy", "naic_code", "NAIC Code"),
            ("policy", "effective_date", "Effective Date"),
            ("policy", "expiration_date", "Expiration Date"),
            ("policy", "form_type", "Form Type"),
            ("policy", "causes_of_loss_form", "Causes of Loss"),
            ("policy", "description_of_operations", "Description of Operations"),
            ("policy", "program", "Program"),
            # Insured section
            ("named_insured", "name", "Named Insured"),
            ("named_insured", "dba", "DBA"),
            ("named_insured", "entity_type", "Entity Type"),
            ("named_insured__address", "street", "Street Address"),
            ("named_insured__address", "city", "City"),
            ("named_insured__address", "state", "State"),
            ("named_insured__address", "zip", "ZIP Code"),
            ("named_insured", "phone", "Phone"),
            ("named_insured", "email", "Email"),
            # Coverages section
            ("coverages", "building_limit", "Building Limit"),
            ("coverages", "bpp_limit", "Business Personal Property"),
            ("coverages", "bi_limit", "Business Income"),
            ("coverages", "extra_expense_limit", "Extra Expense"),
            ("coverages", "deductible", "Deductible"),
            ("coverages", "wind_hail_deductible", "Wind/Hail Deductible"),
            ("coverages", "coinsurance", "Coinsurance"),
            ("coverages", "replacement_cost", "Replacement Cost"),
            ("coverages", "agreed_value", "Agreed Value"),
            ("coverages", "flood_coverage", "Flood Coverage"),
            ("coverages", "earthquake_coverage", "Earthquake Coverage"),
            ("coverages", "ordinance_or_law", "Ordinance or Law"),
            # Premium section
            ("premium", "total_premium", "Total Premium"),
            ("premium", "building_premium", "Building Premium"),
            ("premium", "bpp_premium", "BPP Premium"),
            ("premium", "bi_premium", "BI Premium"),
            ("premium", "taxes", "Taxes"),
            ("premium", "fees", "Fees & Surcharges"),
            ("premium", "minimum_earned_premium", "Min. Earned Premium"),
            ("premium", "payment_plan", "Payment Plan"),
            # Agent section
            ("agent", "name", "Agent Name"),
            ("agent", "agency", "Agency"),
            ("agent", "phone", "Agent Phone"),
            ("agent", "email", "Agent Email"),
            ("agent", "license_number", "License Number"),
            # Mortgagee section
            ("mortgagee", "name", "Mortgagee / Lienholder"),
            ("mortgagee", "loan_number", "Loan Number"),
            ("mortgagee", "address", "Mortgagee Address"),
        ]

        total_fields = len(field_order)
        sent = 0

        for section, field, label in field_order:
            # Resolve nested address
            if "__" in section:
                parts = section.split("__")
                value = policy_data.get(parts[0], {}).get(parts[1], {}).get(field)
                data_key = f"{parts[0]}__{parts[1]}.{field}"
            else:
                value = policy_data.get(section, {}).get(field)
                data_key = f"{section}.{field}"

            if value:
                _push(session_id, {
                    "type": "field",
                    "key": data_key,
                    "value": str(value),
                    "label": label,
                    "section": section.split("__")[0],
                    "progress": round((sent + 1) / total_fields * 100),
                })
            sent += 1

        # Stream locations separately
        for i, loc in enumerate(policy_data.get("locations", [])[:5]):
            _push(session_id, {
                "type": "location",
                "index": i,
                "data": loc,
                "progress": 100,
            })

        _push(session_id, {"type": "complete", "data": policy_data})

    except Exception as exc:
        _push(session_id, {"type": "error", "message": str(exc)})


@app.route("/")
def index():
    return render_template("ams.html")


@app.route("/api/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files are supported"}), 400

    session_id = str(uuid.uuid4())
    safe_name = f"{session_id}_{file.filename}"
    filepath = POLICIES_DIR / safe_name
    file.save(filepath)

    thread = threading.Thread(target=_run_extraction, args=(session_id, str(filepath)), daemon=True)
    thread.start()

    return jsonify({"session_id": session_id, "filename": file.filename})


@app.route("/api/stream/<session_id>")
def stream(session_id: str):
    q = _get_queue(session_id)

    def generate():
        yield "data: {\"type\": \"connected\"}\n\n"
        while True:
            try:
                event = q.get(timeout=30)
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") in ("complete", "error"):
                    break
            except queue.Empty:
                yield "data: {\"type\": \"ping\"}\n\n"

    return Response(
        generate(),
        content_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    print(f"\n  Broker Agentic Challenge — Mock Applied Epic AMS")
    print(f"  Running at http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=debug, threaded=True)

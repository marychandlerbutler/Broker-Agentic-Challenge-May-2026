import os
import json
import time
import queue
import uuid
import threading
from pathlib import Path
from flask import Flask, render_template, request, jsonify, Response
from dotenv import load_dotenv

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


# ─────────────────────────────────────────────────────────────
# Demo data — used when no ANTHROPIC_API_KEY is configured.
# Riverside Manufacturing LLC, a fictional Commercial Property risk.
# ─────────────────────────────────────────────────────────────
DEMO_POLICY = {
    "named_insured": {
        "name": "Riverside Manufacturing LLC",
        "dba": "Riverside Mfg.",
        "entity_type": "Limited Liability Company",
        "fein": "31-4872910",
        "address": {
            "street": "4821 Industrial Parkway",
            "city": "Columbus",
            "state": "OH",
            "zip": "43215",
        },
        "phone": "(614) 555-0192",
        "email": "operations@riversidemfg.com",
        "sic_code": "3460",
        "years_in_business": "18",
        "annual_revenue": "$12,400,000",
        "num_employees": "87",
        "website": "www.riversidemfg.com",
        "account_executive": "James Whitfield",
        "account_manager": "Sandra Torres",
        "customer_since": "01/15/2007",
    },
    "policy": {
        "policy_number": "CPP-2094-887231",
        "carrier": "Travelers Insurance",
        "naic_code": "25658",
        "program": "Middle Market Commercial",
        "effective_date": "06/01/2025",
        "expiration_date": "06/01/2026",
        "policy_type": "Commercial Property",
        "form_type": "CP 00 10 — Building and Personal Property",
        "causes_of_loss_form": "Special Form",
        "description_of_operations": "Metal fabrication and assembly manufacturing",
        "status": "Active",
        "transaction_type": "New Business",
        "renewal_of": "",
        "policy_fee": "$250",
        "surplus_lines": "No",
        "admitted": "Admitted",
        "audit_frequency": "Annual",
    },
    "coverages": {
        "building_limit": "$3,200,000",
        "bpp_limit": "$850,000",
        "bi_limit": "$500,000",
        "extra_expense_limit": "$500,000",
        "deductible": "$10,000",
        "wind_hail_deductible": "$25,000",
        "flood_coverage": "Not Included",
        "earthquake_coverage": "Not Included",
        "coinsurance": "80%",
        "replacement_cost": "Yes",
        "agreed_value": "No",
        "ordinance_or_law": "Yes — 25%",
        "equipment_breakdown": "Yes — $1,000,000",
        "inflation_guard": "4%",
        "peak_season_increase": "$0",
        "blanket_specific": "Specific",
        "inland_marine": "No",
        "functional_replacement_cost": "No",
        "actual_cash_value": "No",
        "spoilage_coverage": "No",
        "spoilage_limit": "",
        "outdoor_property": "No",
        "outdoor_property_limit": "",
        "signs_coverage": "No",
        "signs_limit": "",
        "glass_coverage": "Yes",
        "glass_limit": "$25,000",
    },
    "locations": [
        {
            "location_number": "1",
            "address": "4821 Industrial Parkway, Columbus, OH 43215",
            "building_value": "$3,200,000",
            "bpp_value": "$850,000",
            "year_built": "1998",
            "construction_type": "Joisted Masonry",
            "occupancy": "Manufacturing",
            "square_footage": "62,500",
            "num_stories": "1",
            "building_description": "Main Manufacturing Facility",
            "roof_type": "Flat",
            "roof_year": "2018",
            "wiring_year": "2015",
            "plumbing_year": "1998",
            "hvac_year": "2020",
            "sprinklered": "Yes",
            "alarm_type": "Central Station",
            "distance_to_hydrant": "150 ft",
            "distance_to_station": "0.8 miles",
            "flood_zone": "X",
            "earthquake_zone": "Zone 2",
        },
    ],
    "premium": {
        "total_premium": "$48,750",
        "building_premium": "$32,400",
        "bpp_premium": "$8,200",
        "bi_premium": "$5,800",
        "taxes": "$1,250",
        "fees": "$1,100",
        "minimum_earned_premium": "$12,187",
        "payment_plan": "Quarterly",
        "agency_commission_pct": "12%",
        "agency_commission_amount": "$5,850",
        "broker_fee": "$0",
        "surplus_lines_tax": "$0",
        "stamping_fee": "$0",
        "down_payment": "$12,187",
        "installment_amount": "$12,187",
        "installment_due_dates": "09/01, 12/01, 03/01",
        "billed_premium": "$48,750",
        "annualized_premium": "$48,750",
        "estimated_premium": "$48,750",
        "auditable_policy": "No",
        "premium_financed": "No",
        "finance_company": "",
        "finance_agreement": "",
        "financed_amount": "",
        "finance_rate": "",
    },
    "agent": {
        "name": "Mary Butler",
        "agency": "Acme Insurance Agency",
        "address": "100 Broker Plaza, Cincinnati, OH 45202",
        "phone": "(513) 555-0177",
        "email": "mary.butler@acmeinsurance.com",
        "license_number": "OH-87245932",
    },
    "mortgagee": {
        "name": "Huntington National Bank",
        "loan_number": "HNB-2019-114882",
        "address": "41 S High St, Columbus, OH 43215",
    },
    "loss_payee": {
        "name": "Huntington National Bank - Loss Payee",
        "address": "41 S High St, Columbus, OH 43215",
    },
    "additional_insured": {
        "name": "Huntington National Bank",
        "relationship": "Lender",
        "certificate_holder": "Applied Power Systems Inc.",
        "waiver_of_subrogation": "Yes",
        "primary_noncontributory": "Yes",
    },
}


FIELD_ORDER = [
    # ── Account tab (Named Insured) ──
    ("named_insured", "name", "Named Insured"),
    ("named_insured", "dba", "DBA"),
    ("named_insured", "entity_type", "Entity Type"),
    ("named_insured", "fein", "FEIN"),
    ("named_insured__address", "street", "Street Address"),
    ("named_insured__address", "city", "City"),
    ("named_insured__address", "state", "State"),
    ("named_insured__address", "zip", "ZIP Code"),
    ("named_insured", "phone", "Phone"),
    ("named_insured", "email", "Email"),
    # ── Account tab (Business Information) ──
    ("named_insured", "sic_code", "SIC Code"),
    ("named_insured", "years_in_business", "Years in Business"),
    ("named_insured", "annual_revenue", "Annual Revenue"),
    ("named_insured", "num_employees", "Number of Employees"),
    ("named_insured", "website", "Website"),
    ("named_insured", "account_executive", "Account Executive"),
    ("named_insured", "account_manager", "Account Manager"),
    ("named_insured", "customer_since", "Customer Since"),
    # ── Policy tab ──
    ("policy", "policy_number", "Policy Number"),
    ("policy", "carrier", "Insurance Carrier"),
    ("policy", "naic_code", "NAIC Code"),
    ("policy", "effective_date", "Effective Date"),
    ("policy", "expiration_date", "Expiration Date"),
    ("policy", "form_type", "Form Type"),
    ("policy", "causes_of_loss_form", "Causes of Loss"),
    ("policy", "description_of_operations", "Description of Operations"),
    ("policy", "program", "Program"),
    # ── Policy tab (Policy Administration) ──
    ("policy", "status", "Policy Status"),
    ("policy", "transaction_type", "Transaction Type"),
    ("policy", "renewal_of", "Renewal Of"),
    ("policy", "policy_fee", "Policy Fee"),
    ("policy", "surplus_lines", "Surplus Lines"),
    ("policy", "admitted", "Admitted / Non-Admitted"),
    ("policy", "audit_frequency", "Audit Frequency"),
    # ── Coverages tab ──
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
    # ── Additional Coverages (still on Coverages tab) ──
    ("coverages", "ordinance_or_law", "Ordinance or Law"),
    ("coverages", "equipment_breakdown", "Equipment Breakdown"),
    ("coverages", "inflation_guard", "Inflation Guard"),
    ("coverages", "peak_season_increase", "Peak Season Increase"),
    ("coverages", "blanket_specific", "Blanket / Specific"),
    ("coverages", "inland_marine", "Inland Marine"),
    ("coverages", "functional_replacement_cost", "Functional Replacement Cost"),
    ("coverages", "actual_cash_value", "Actual Cash Value"),
    # ── Special Coverages (Coverages tab) ──
    ("coverages", "spoilage_coverage", "Spoilage Coverage"),
    ("coverages", "spoilage_limit", "Spoilage Limit"),
    ("coverages", "outdoor_property", "Outdoor Property"),
    ("coverages", "outdoor_property_limit", "Outdoor Property Limit"),
    ("coverages", "signs_coverage", "Signs Coverage"),
    ("coverages", "signs_limit", "Signs Limit"),
    ("coverages", "glass_coverage", "Glass Coverage"),
    ("coverages", "glass_limit", "Glass Limit"),
    # ── Premium tab ──
    ("premium", "total_premium", "Total Premium"),
    ("premium", "building_premium", "Building Premium"),
    ("premium", "bpp_premium", "BPP Premium"),
    ("premium", "bi_premium", "BI Premium"),
    ("premium", "taxes", "Taxes"),
    ("premium", "fees", "Fees & Surcharges"),
    ("premium", "minimum_earned_premium", "Min. Earned Premium"),
    ("premium", "payment_plan", "Payment Plan"),
    # ── Agency Compensation (Premium tab) ──
    ("premium", "agency_commission_pct", "Commission %"),
    ("premium", "agency_commission_amount", "Commission Amount"),
    ("premium", "broker_fee", "Broker Fee"),
    ("premium", "surplus_lines_tax", "Surplus Lines Tax"),
    ("premium", "stamping_fee", "Stamping Fee"),
    # ── Billing & Installments (Premium tab) ──
    ("premium", "down_payment", "Down Payment"),
    ("premium", "installment_amount", "Installment Amount"),
    ("premium", "installment_due_dates", "Installment Due Dates"),
    # -- Premium Breakdown additions --
    ("premium", "billed_premium", "Billed Premium"),
    ("premium", "annualized_premium", "Annualized Premium"),
    ("premium", "estimated_premium", "Estimated Premium"),
    ("premium", "auditable_policy", "Auditable Policy"),
    # -- Premium Finance --
    ("premium", "premium_financed", "Premium Financed"),
    ("premium", "finance_company", "Finance Company"),
    ("premium", "finance_agreement", "Finance Agreement #"),
    ("premium", "financed_amount", "Financed Amount"),
    ("premium", "finance_rate", "Finance Rate %"),
    # ── Agent / Mortgagee tab ──
    ("agent", "name", "Agent Name"),
    ("agent", "agency", "Agency"),
    ("agent", "phone", "Agent Phone"),
    ("agent", "email", "Agent Email"),
    ("agent", "license_number", "License Number"),
    ("mortgagee", "name", "Mortgagee / Lienholder"),
    ("mortgagee", "loan_number", "Loan Number"),
    ("mortgagee", "address", "Mortgagee Address"),
    # ── Loss Payee (Agent tab) ──
    ("loss_payee", "name", "Loss Payee Name"),
    ("loss_payee", "address", "Loss Payee Address"),
    # ── Additional Insured (Agent tab) ──
    ("additional_insured", "name", "Additional Insured Name"),
    ("additional_insured", "relationship", "Relationship"),
    ("additional_insured", "certificate_holder", "Certificate Holder"),
    ("additional_insured", "waiver_of_subrogation", "Waiver of Subrogation"),
    ("additional_insured", "primary_noncontributory", "Primary & Non-Contributory"),
]


def _resolve(data: dict, section: str, field: str):
    if "__" in section:
        parent, child = section.split("__", 1)
        return data.get(parent, {}).get(child, {}).get(field)
    return data.get(section, {}).get(field)


def _stream_policy(session_id: str, policy_data: dict, per_field_delay: float = 0.0):
    total = len(FIELD_ORDER)
    for sent, (section, field, label) in enumerate(FIELD_ORDER):
        value = _resolve(policy_data, section, field)
        if "__" in section:
            parent, child = section.split("__", 1)
            data_key = f"{parent}__{child}.{field}"
        else:
            data_key = f"{section}.{field}"

        if value:
            _push(session_id, {
                "type": "field",
                "key": data_key,
                "value": str(value),
                "label": label,
                "section": section.split("__")[0],
                "progress": round((sent + 1) / total * 100),
            })
            if per_field_delay:
                time.sleep(per_field_delay)

    for i, loc in enumerate(policy_data.get("locations", [])[:5]):
        _push(session_id, {
            "type": "location",
            "index": i,
            "data": loc,
            "progress": 100,
        })

    _push(session_id, {"type": "complete", "data": policy_data})


def _run_demo(session_id: str, filepath: str):
    try:
        _push(session_id, {"type": "status", "phase": "reading", "message": "Agent reading policy..."})
        time.sleep(1.6)
        _push(session_id, {"type": "status", "phase": "extracting", "message": "Extracting data with Claude AI..."})
        time.sleep(2.4)
        _push(session_id, {"type": "status", "phase": "populating", "message": "Populating AMS..."})
        time.sleep(0.8)
        _stream_policy(session_id, DEMO_POLICY, per_field_delay=0.08)
    except Exception as exc:
        _push(session_id, {"type": "error", "message": str(exc)})


def _run_live(session_id: str, filepath: str):
    from agent.policy_extractor import PolicyExtractor
    try:
        _push(session_id, {"type": "status", "phase": "reading", "message": "Agent reading policy..."})
        _push(session_id, {"type": "status", "phase": "extracting", "message": "Extracting data with Claude AI..."})
        extractor = PolicyExtractor()
        policy_data = extractor.extract(filepath)
        _push(session_id, {"type": "status", "phase": "populating", "message": "Populating AMS..."})
        _stream_policy(session_id, policy_data)
    except Exception as exc:
        _push(session_id, {"type": "error", "message": str(exc)})


def _run_extraction(session_id: str, filepath: str):
    if os.getenv("ANTHROPIC_API_KEY"):
        _run_live(session_id, filepath)
    else:
        _run_demo(session_id, filepath)


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

    return jsonify({
        "session_id": session_id,
        "filename": file.filename,
        "mode": "live" if os.getenv("ANTHROPIC_API_KEY") else "demo",
    })


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
    mode = "LIVE (Claude AI)" if os.getenv("ANTHROPIC_API_KEY") else "DEMO (no API key)"
    print(f"\n  Broker Agentic Challenge — Mock Applied Epic AMS")
    print(f"  Mode: {mode}")
    print(f"  Running at http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=debug, threaded=True)

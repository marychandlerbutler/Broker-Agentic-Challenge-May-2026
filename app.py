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
# Two policies rotate on each upload.
# ─────────────────────────────────────────────────────────────

DEMO_POLICIES = [
{  # Policy 0 — Lincoln County, MS (Travelers)
    "named_insured": {
        "name": "LINCOLN COUNTY",
        "dba": "",
        "entity_type": "Government Entity",
        "fein": "64-6001452",
        "address": {
            "street": "1200 Government Plaza",
            "city": "Brookhaven",
            "state": "MS",
            "zip": "39601",
        },
        "phone": "(601) 835-3400",
        "email": "admin@lincolncountyms.gov",
        "sic_code": "9199",
        "years_in_business": "150+",
        "annual_revenue": "$12,500,000",
        "num_employees": "187",
        "website": "www.lincolncountyms.gov",
        "account_executive": "Sarah Mitchell",
        "account_manager": "James Tanner",
        "customer_since": "01/01/2010",
    },
    "policy": {
        "policy_number": "H-630-7741X298-TIL-25",
        "carrier": "Travelers Property Casualty Company of America",
        "naic_code": "25658",
        "program": "Counties Guaranteed Cost",
        "effective_date": "06/01/2024",
        "expiration_date": "06/01/2025",
        "form_type": "Commercial Package",
        "causes_of_loss_form": "Special",
        "description_of_operations": "County Government Operations",
        "status": "Active",
        "transaction_type": "Renewal",
        "renewal_of": "H-630-7741X298-TIL-24",
        "policy_fee": "$0",
        "surplus_lines": "No",
        "admitted": "Admitted",
        "audit_frequency": "Annual",
        "billing_type": "Agency Bill",
        "lob_code": "CPROP",
        "source_code": "Renewal",
        "branch_structure": "Sansouth / Jackson MS",
    },
    "coverages": {
        "building_limit": "$62,000,000",
        "bpp_limit": "Included in Blanket",
        "bi_limit": "$850,000",
        "extra_expense_limit": "$50,000",
        "deductible": "$25,000",
        "wind_hail_deductible": "$25,000",
        "coinsurance": "No Coinsurance",
        "replacement_cost": "Yes",
        "agreed_value": "No",
        "flood_coverage": "$5,000,000 / $10,000 Ded.",
        "earthquake_coverage": "$8,000,000 / $10,000 Ded.",
        "ordinance_or_law": "$250,000",
        "equipment_breakdown": "Included",
        "inflation_guard": "No",
        "peak_season_increase": "No",
        "blanket_specific": "Blanket",
        "inland_marine": "Yes",
        "functional_replacement_cost": "No",
        "actual_cash_value": "No",
        "rental_value": "Included",
        "blanket_building": "$62,000,000",
        "blanket_pers_prop": "Included",
        "crime_coverage": "Yes",
        "crime_limit": "$100,000",
        "inland_marine_type": "Contractors Equipment",
        "coverage_code": "CPROP-BL",
        "line_premium": "$121,500",
        "spoilage_coverage": "No",
        "spoilage_limit": "",
        "outdoor_property": "Yes",
        "outdoor_property_limit": "$50,000",
        "signs_coverage": "Yes",
        "signs_limit": "$50,000",
        "glass_coverage": "No",
        "glass_limit": "",
    },
    "premium": {
        "building_premium": "$108,200",
        "bpp_premium": "Included",
        "bi_premium": "$8,500",
        "taxes": "$0",
        "fees": "$0",
        "minimum_earned_premium": "$37,125",
        "payment_plan": "Annual",
        "billed_premium": "$148,500",
        "annualized_premium": "$148,500",
        "estimated_premium": "$148,500",
        "auditable_policy": "No",
        "total_premium": "$148,500",
        "agency_commission_pct": "10%",
        "agency_commission_amount": "$14,850",
        "broker_fee": "$0",
        "surplus_lines_tax": "$0",
        "stamping_fee": "$0",
        "down_payment": "$148,500",
        "installment_amount": "N/A",
        "installment_due_dates": "N/A",
        "premium_financed": "No",
        "finance_company": "",
        "finance_agreement": "",
        "financed_amount": "",
        "finance_rate": "",
    },
    "agent": {
        "name": "Robert Baucum",
        "agency": "Magnolia Insurance Group",
        "phone": "(601) 922-5500",
        "email": "rbaucum@magnoliainsurance.com",
        "license_number": "MS-1042387",
    },
    "mortgagee": {
        "name": "",
        "loan_number": "",
        "address": "",
    },
    "loss_payee": {
        "name": "",
        "address": "",
    },
    "additional_insured": {
        "name": "Lincoln County Board of Supervisors",
        "relationship": "County Board",
        "certificate_holder": "Yes",
        "waiver_of_subrogation": "Yes",
        "primary_noncontributory": "Yes",
        "interest_type_code": "AI",
        "priority_rank": "1",
    },
    "binder": {
        "binder_number": "",
        "binder_effective_date": "",
        "binder_expiration_date": "",
    },
    "remarks": {
        "special_conditions": "Blanket coverage applies to all 8 scheduled locations. Flood coverage split: $5M aggregate for locations 1-6, $1M for locations 7-8. Business Income includes 60-day ordinary payroll limitation. Utility Services - Direct Damage covered up to $100,000.",
    },
},
{  # Policy 1 — Greenfield Rural Water District (US Specialty)
    "named_insured": {
        "name": "GREENFIELD RURAL WATER DISTRICT",
        "dba": "",
        "entity_type": "Government Entity",
        "fein": "62-1234567",
        "address": {
            "street": "850 Water Tower Rd",
            "city": "Greenfield",
            "state": "TN",
            "zip": "38230",
        },
        "phone": "(731) 235-4100",
        "email": "admin@greenfieldwater.org",
        "sic_code": "4941",
        "years_in_business": "45",
        "annual_revenue": "$3,200,000",
        "num_employees": "22",
        "website": "www.greenfieldwater.org",
        "account_executive": "Sarah Mitchell",
        "account_manager": "James Tanner",
        "customer_since": "04/01/2018",
    },
    "policy": {
        "policy_number": "U24PKG81155-01",
        "carrier": "U.S. Specialty Insurance Company",
        "naic_code": "22608",
        "program": "Public Risk Package",
        "effective_date": "04/01/2024",
        "expiration_date": "04/01/2025",
        "form_type": "Commercial Package",
        "causes_of_loss_form": "Special",
        "description_of_operations": "Rural Water District / Governmental Subdivision",
        "status": "Active",
        "transaction_type": "Renewal",
        "renewal_of": "U23PKG81155-01",
        "policy_fee": "$0",
        "surplus_lines": "No",
        "admitted": "Admitted",
        "audit_frequency": "Annual",
        "billing_type": "Agency Bill",
        "lob_code": "CPROP",
        "source_code": "Renewal",
        "branch_structure": "Public Risk / Houston TX",
    },
    "coverages": {
        "building_limit": "$8,750,000",
        "bpp_limit": "Included",
        "bi_limit": "Not Covered",
        "extra_expense_limit": "Not Covered",
        "deductible": "$2,500",
        "wind_hail_deductible": "Not Covered",
        "coinsurance": "No Coinsurance",
        "replacement_cost": "Yes",
        "agreed_value": "Yes",
        "flood_coverage": "$750,000 / $50,000 Ded.",
        "earthquake_coverage": "$4,000,000 / $25,000 Ded.",
        "ordinance_or_law": "Not Covered",
        "equipment_breakdown": "Included",
        "inflation_guard": "No",
        "peak_season_increase": "No",
        "blanket_specific": "Specific",
        "inland_marine": "Yes",
        "functional_replacement_cost": "No",
        "actual_cash_value": "No",
        "rental_value": "Not Covered",
        "blanket_building": "N/A",
        "blanket_pers_prop": "N/A",
        "crime_coverage": "Yes",
        "crime_limit": "$50,000",
        "inland_marine_type": "Scheduled Equipment",
        "coverage_code": "CPROP-SP",
        "line_premium": "$18,750",
        "spoilage_coverage": "No",
        "spoilage_limit": "",
        "outdoor_property": "No",
        "outdoor_property_limit": "",
        "signs_coverage": "No",
        "signs_limit": "",
        "glass_coverage": "No",
        "glass_limit": "",
    },
    "premium": {
        "building_premium": "$16,200",
        "bpp_premium": "Included",
        "bi_premium": "Not Covered",
        "taxes": "$0",
        "fees": "$404",
        "minimum_earned_premium": "$6,750",
        "payment_plan": "Annual",
        "billed_premium": "$22,854",
        "annualized_premium": "$22,854",
        "estimated_premium": "$22,854",
        "auditable_policy": "No",
        "total_premium": "$22,854",
        "agency_commission_pct": "12%",
        "agency_commission_amount": "$2,700",
        "broker_fee": "$0",
        "surplus_lines_tax": "$0",
        "stamping_fee": "$0",
        "down_payment": "$22,854",
        "installment_amount": "N/A",
        "installment_due_dates": "N/A",
        "premium_financed": "No",
        "finance_company": "",
        "finance_agreement": "",
        "financed_amount": "",
        "finance_rate": "",
    },
    "agent": {
        "name": "David Whitfield",
        "agency": "Bluegrass Risk Advisors",
        "phone": "(615) 340-2200",
        "email": "dwhitfield@bluegrassrisk.com",
        "license_number": "TN-0198432",
    },
    "mortgagee": {
        "name": "USDA Rural Development",
        "loan_number": "RD-TN-2018-0042",
        "address": "1400 Independence Ave SW, Washington DC 20250",
    },
    "loss_payee": {
        "name": "USDA Rural Development",
        "address": "1400 Independence Ave SW, Washington DC 20250",
    },
    "additional_insured": {
        "name": "Greenfield Water District Board",
        "relationship": "District Board",
        "certificate_holder": "Yes",
        "waiver_of_subrogation": "Yes",
        "primary_noncontributory": "No",
        "interest_type_code": "AI",
        "priority_rank": "1",
    },
    "binder": {
        "binder_number": "",
        "binder_effective_date": "",
        "binder_expiration_date": "",
    },
    "remarks": {
        "special_conditions": "Package policy includes GL, Property, Inland Marine, EDP, Crime, Auto, and Excess. Property on specific scheduled basis per schedule on file. Flood and Earthquake are additional coverages with separate limits and deductibles. USDA Rural Development noted as mortgagee and loss payee per loan agreement RD-TN-2018-0042. TRIA coverage included at $175.",
    },
},
]


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
    ("policy", "billing_type", "Billing Type"),
    ("policy", "lob_code", "LOB Code"),
    ("policy", "source_code", "Source Code"),
    ("policy", "branch_structure", "Branch / Structure"),
    # ── Coverages tab ──
    ("coverages", "total_property_limit", "Total Property Limit"),
    ("coverages", "blanket_or_specific", "Blanket / Specific"),
    ("coverages", "building_limit", "Building Limit"),
    ("coverages", "bpp_limit", "Business Personal Property"),
    ("coverages", "bi_limit", "Business Income"),
    ("coverages", "extra_expense_limit", "Extra Expense"),
    ("coverages", "deductible", "Standard Deductible"),
    ("coverages", "wind_hail_deductible", "Wind/Hail Deductible"),
    ("coverages", "flood_limit", "Flood Limit"),
    ("coverages", "flood_deductible", "Flood Deductible"),
    ("coverages", "earthquake_limit", "Earthquake Limit"),
    ("coverages", "earthquake_deductible", "Earthquake Deductible"),
    ("coverages", "num_locations", "Number of Locations"),
    ("coverages", "valuation_method", "Valuation Method"),
    ("coverages", "coinsurance", "Coinsurance"),
    ("coverages", "replacement_cost", "Replacement Cost"),
    ("coverages", "agreed_value", "Agreed Value"),
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
    # ── AL3 Coverages additions ──
    ("coverages", "rental_value", "Rental Value"),
    ("coverages", "blanket_building", "Blanket Building"),
    ("coverages", "blanket_pers_prop", "Blanket Pers. Prop"),
    ("coverages", "crime_coverage", "Crime Coverage"),
    ("coverages", "crime_limit", "Crime Limit"),
    ("coverages", "inland_marine_type", "Inland Marine Type"),
    ("coverages", "coverage_code", "Coverage Code"),
    ("coverages", "line_premium", "Line Premium"),
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
    ("additional_insured", "interest_type_code", "Interest Type Code"),
    ("additional_insured", "priority_rank", "Priority / Rank"),
    # ── Binder Information (Additional Interests tab) ──
    ("binder", "binder_number", "Binder Number"),
    ("binder", "binder_effective_date", "Binder Effective Date"),
    ("binder", "binder_expiration_date", "Binder Expiration Date"),
    # ── Remarks (Additional Interests tab) ──
    ("remarks", "special_conditions", "Special Conditions"),
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
    filename = Path(filepath).name
    if any(kw in filename for kw in ("Greenfield", "Specialty", "USSpecialty")):
        policy = DEMO_POLICIES[1]
    else:
        policy = DEMO_POLICIES[0]  # Lincoln County default
    try:
        _push(session_id, {"type": "status", "phase": "reading", "message": "Agent reading policy..."})
        time.sleep(1.6)
        _push(session_id, {"type": "status", "phase": "extracting", "message": "Extracting data with Claude AI..."})
        time.sleep(2.4)
        _push(session_id, {"type": "status", "phase": "populating", "message": "Populating AMS..."})
        time.sleep(0.8)
        _stream_policy(session_id, policy, per_field_delay=0.08)
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

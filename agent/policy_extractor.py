import base64
import json
import re
import os
import anthropic

EXTRACTION_PROMPT = """You are an expert insurance policy analyst specializing in Commercial Property insurance.

Carefully read the attached PDF insurance policy and extract ALL relevant information.
Return ONLY a valid JSON object — no markdown fences, no explanation, just raw JSON.

═══════════════════════════════════════════════════════
CARRIER FORMAT RECOGNITION
═══════════════════════════════════════════════════════

First, identify which carrier format this policy uses:

FORMAT A — U.S. Specialty Insurance Company (Public Risk):
  - Policy number begins with "U" followed by digits (e.g. U23PKG80466-01)
  - Has a "RENEWAL CERTIFICATE" cover page with "Policy No." label
  - Property section titled "BUILDING AND PERSONAL PROPERTY COVERAGE FORM - SUPPLEMENTAL DECLARATIONS"
  - Building + BPP shown as a SINGLE combined line: "Building + Personal Property" with one dollar amount
  - Flood and Earthquake appear as "ADDITIONAL COVERAGES" with separate deductible/SIR columns
    labeled "Any One [Flood/Earthquake]" and "Annual Aggregate"
  - Standard deductible labeled "DEDUCTIBLE / SELF-INSURED RETENTION Applicable to coverages
    other than Flood or Earthquake"
  - Agent info on cover page under "AGENT NAME AND ADDRESS"
  - Policy period on cover page: "POLICY PERIOD: From: [date] To: [date]"

FORMAT B — Travelers (Deluxe Property Coverage Form):
  - Policy number follows pattern P-630-XXXXXXX-TRV/TCT or H-630-XXXXXXX-TIL (e.g. P-630-0696L948-TRV-17)
  - Two sub-formats:
    B1 SPECIFIC LIMITS: Building and BPP listed separately per location/building on schedule "DX 00 03"
    B2 BLANKET: Single combined limit labeled "Building(s) and Your Business Personal Property"
       under "COVERAGES AND LIMITS OF INSURANCE - DESCRIBED PREMISES"
  - Flood labeled "CAUSES OF LOSS - BROAD FORM FLOOD" with "Annual Aggregate Limit" by building range
  - Earthquake labeled "CAUSES OF LOSS - EARTHQUAKE" with "Annual Aggregate Limit" by building range
  - Wind/Hail deductible is a PERCENTAGE with a minimum dollar amount per occurrence (varies by state)
  - Standard deductible labeled "ANY OTHER COVERED LOSS in any one occurrence"
  - Business Income under "DELUXE BUSINESS INCOME (AND EXTRA EXPENSE) COVERAGE FORM - DESCRIBED PREMISES"
  - Agent info on Common Policy Declarations page as "NAME AND ADDRESS OF AGENT OR BROKER"
  - Multiple locations on "LOCATION SCHEDULE" (IL T0 03)

═══════════════════════════════════════════════════════
EXTRACTION RULES BY FIELD
═══════════════════════════════════════════════════════

POLICY NUMBER:
  Format A: Read from "Policy No." on the RENEWAL CERTIFICATE cover page
  Format B: Read from the Common Policy Declarations page

TOTAL PROPERTY LIMIT (total_property_limit):
  Format A: The single "Building + Personal Property" combined dollar amount — this IS the total limit
  Format B B1 (Specific): Sum ALL individual building limits across all locations/buildings, then
    sum ALL BPP limits across all locations/buildings. Set building_limit to the building total,
    bpp_limit to the BPP total, and total_property_limit to their combined sum.
  Format B B2 (Blanket): The single "Building(s) and Your Business Personal Property" blanket
    amount is the total_property_limit. Set building_limit and bpp_limit both to null.

BLANKET vs SPECIFIC (blanket_or_specific):
  Format A: "Specific" (combined building+BPP line is still location-specific)
  Format B B1: "Specific"
  Format B B2: "Blanket"

STANDARD DEDUCTIBLE (deductible):
  Format A: The amount under "DEDUCTIBLE / SELF-INSURED RETENTION Applicable to coverages
    other than Flood or Earthquake"
  Format B: The amount labeled "ANY OTHER COVERED LOSS in any one occurrence"

WIND/HAIL DEDUCTIBLE (wind_hail_deductible):
  Format B: Store as "X% (min $Y,YYY)" — e.g. "5% (min $50,000)"
  Format A: Use the standard deductible if no separate wind deductible is stated

FLOOD LIMIT (flood_limit) and FLOOD DEDUCTIBLE (flood_deductible):
  Format A: Read from "ADDITIONAL COVERAGES" — flood section. "Any One" column = per-occurrence
    deductible/SIR; "Annual Aggregate" column = annual aggregate limit. If flood is not listed
    or shows $0, set flood_limit to "Not Covered" and flood_deductible to null.
  Format B: "Annual Aggregate Limit" from "CAUSES OF LOSS - BROAD FORM FLOOD" section.
    If absent, set flood_limit to "Not Covered".

EARTHQUAKE LIMIT and EARTHQUAKE DEDUCTIBLE:
  Same logic as flood but for earthquake sections.

BUSINESS INCOME LIMIT (bi_limit):
  Format B: Read from "DELUXE BUSINESS INCOME (AND EXTRA EXPENSE) COVERAGE FORM"
  Format A: Extract if present, otherwise null

AGENT NAME (agent.name):
  Format A: From "AGENT NAME AND ADDRESS" on the cover page — extract the agent/agency name only
  Format B: From "NAME AND ADDRESS OF AGENT OR BROKER" on Common Policy Declarations

NUMBER OF LOCATIONS (num_locations):
  Count every distinct location listed on the policy (Location Schedule or declarations pages).
  Store as an integer.

VALUATION METHOD (valuation_method):
  Look for "Replacement Cost", "Actual Cash Value", or "ACV" anywhere in the declarations.
  Return "Replacement Cost" or "Actual Cash Value".

COINSURANCE (coinsurance):
  If a coinsurance percentage appears, return "Yes — X%". If explicitly waived or absent, "No".

SPECIAL FLAGS:
  - If a field shows "Per Schedule on File" or similar language, store as "See Schedule"
  - If Flood or Earthquake coverage is absent or $0, store flood_limit / earthquake_limit
    as "Not Covered" (do not leave null — explicitly populate these fields)

═══════════════════════════════════════════════════════
JSON OUTPUT STRUCTURE
═══════════════════════════════════════════════════════

Use this exact structure (set any truly missing field to null):

{
  "named_insured": {
    "name": null,
    "dba": null,
    "entity_type": null,
    "address": {
      "street": null,
      "city": null,
      "state": null,
      "zip": null
    },
    "phone": null,
    "email": null
  },
  "policy": {
    "policy_number": null,
    "carrier": null,
    "naic_code": null,
    "program": null,
    "effective_date": null,
    "expiration_date": null,
    "policy_type": null,
    "form_type": null,
    "causes_of_loss_form": null,
    "description_of_operations": null
  },
  "coverages": {
    "building_limit": null,
    "bpp_limit": null,
    "total_property_limit": null,
    "blanket_or_specific": null,
    "bi_limit": null,
    "extra_expense_limit": null,
    "deductible": null,
    "wind_hail_deductible": null,
    "flood_limit": null,
    "flood_deductible": null,
    "earthquake_limit": null,
    "earthquake_deductible": null,
    "coinsurance": null,
    "replacement_cost": null,
    "valuation_method": null,
    "agreed_value": null,
    "ordinance_or_law": null,
    "num_locations": null
  },
  "locations": [
    {
      "location_number": null,
      "address": null,
      "building_value": null,
      "bpp_value": null,
      "year_built": null,
      "construction_type": null,
      "occupancy": null,
      "square_footage": null,
      "num_stories": null
    }
  ],
  "premium": {
    "total_premium": null,
    "building_premium": null,
    "bpp_premium": null,
    "bi_premium": null,
    "taxes": null,
    "fees": null,
    "minimum_earned_premium": null,
    "payment_plan": null
  },
  "agent": {
    "name": null,
    "agency": null,
    "address": null,
    "phone": null,
    "email": null,
    "license_number": null
  },
  "mortgagee": {
    "name": null,
    "loan_number": null,
    "address": null
  }
}

═══════════════════════════════════════════════════════
FORMATTING RULES
═══════════════════════════════════════════════════════
- Dollar amounts: use $ with commas, e.g. "$1,250,000"
- Dates: MM/DD/YYYY
- Phone numbers: (XXX) XXX-XXXX
- Yes/No fields: "Yes" or "No"
- Wind/Hail deductible percentage: "X% (min $Y,YYY)" format
- Flood/Earthquake not covered: "Not Covered" (never null for these two fields)
- "Per Schedule on File" language: store as "See Schedule"
- num_locations: integer (e.g. 3), not a string
- Extract every location listed on the policy into the locations array
- If a field truly does not appear anywhere in the document, leave it null
"""


class PolicyExtractor:
    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")
        self.client = anthropic.Anthropic(api_key=api_key)

    def extract(self, pdf_path: str) -> dict:
        with open(pdf_path, "rb") as f:
            pdf_b64 = base64.standard_b64encode(f.read()).decode("utf-8")

        message = self.client.messages.create(
            model="claude-opus-4-5",
            max_tokens=8192,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": pdf_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": EXTRACTION_PROMPT,
                        },
                    ],
                }
            ],
        )

        raw = message.content[0].text.strip()

        # Strip markdown fences if the model added them despite instructions
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        return json.loads(raw)

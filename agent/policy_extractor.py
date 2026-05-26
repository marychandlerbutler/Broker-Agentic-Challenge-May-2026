import base64
import json
import re
import os
import anthropic

EXTRACTION_PROMPT = """You are an expert insurance policy analyst specializing in Commercial Property insurance.

Carefully read the attached PDF insurance policy and extract ALL relevant information.
Return ONLY a valid JSON object — no markdown fences, no explanation, just raw JSON.

Use this exact structure (set any missing field to null):

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
    "bi_limit": null,
    "extra_expense_limit": null,
    "deductible": null,
    "wind_hail_deductible": null,
    "flood_coverage": null,
    "earthquake_coverage": null,
    "coinsurance": null,
    "replacement_cost": null,
    "agreed_value": null,
    "ordinance_or_law": null
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

Important extraction rules:
- Format all dollar amounts with $ and commas, e.g. "$1,250,000"
- Format dates as MM/DD/YYYY
- Format phone numbers as (XXX) XXX-XXXX
- For Yes/No fields use "Yes" or "No"
- Extract every location listed on the policy
- If a field truly does not appear in the document, leave it null
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
            max_tokens=4096,
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

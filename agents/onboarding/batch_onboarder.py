"""
BATCH ONBOARDER — imports multiple SMEs from CSV file.
BOUNDARY: onboards only. Never checks compliance.
"""
import csv
from pathlib import Path
from ..base import BaseAgent
from .onboarding_orchestrator import OnboardingOrchestrator


class BatchOnboarder(BaseAgent):
    name = "batch_onboarder"
    boundary = "Onboards SMEs from CSV only. Never checks compliance."

    REQUIRED_FIELDS = ["pin", "name", "business_type", "industry", "turnover_bracket"]
    OPTIONAL_FIELDS = {
        "business_name": None,
        "county": "Nairobi",
        "annual_turnover_kes": 0,
        "has_employees": "false",
        "employee_count": "0",
        "is_vat_registered": "false",
        "has_etims": "false",
        "phone": "",
        "email": None,
        "preferred_language": "en",
        "preferred_channel": "whatsapp",
        "rental_income_annual_kes": None,
    }

    def import_csv(self, csv_path: str | Path) -> dict:
        """Import SMEs from a CSV file.

        Returns:
            dict with 'success', 'failed', 'skipped' counts and details.
        """
        csv_path = Path(csv_path)
        if not csv_path.exists():
            self.log(f"CSV file not found: {csv_path}", "ERROR")
            return {"success": 0, "failed": 0, "skipped": 0, "errors": [f"File not found: {csv_path}"]}

        self.log(f"=== BATCH IMPORT START: {csv_path.name} ===")

        results = {"success": 0, "failed": 0, "skipped": 0, "errors": [], "imported": []}
        onboarder = OnboardingOrchestrator()

        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)

            # Validate headers
            if reader.fieldnames is None:
                results["errors"].append("CSV has no headers")
                return results

            headers = [h.strip().lower() for h in reader.fieldnames]
            missing = [f for f in self.REQUIRED_FIELDS if f not in headers]
            if missing:
                results["errors"].append(f"Missing required columns: {', '.join(missing)}")
                return results

            for row_num, row in enumerate(reader, start=2):
                # Normalize keys
                row = {k.strip().lower(): v.strip() if v else "" for k, v in row.items()}

                pin = row.get("pin", "").upper()
                name = row.get("name", "")

                if not pin or not name:
                    results["failed"] += 1
                    results["errors"].append(f"Row {row_num}: Missing PIN or name")
                    continue

                # Check if already onboarded
                existing = self.load_sme(pin)
                if existing:
                    results["skipped"] += 1
                    self.log(f"Skipping {pin} — already onboarded")
                    continue

                # Build data dict
                data = self._row_to_data(row)

                try:
                    profile = onboarder.onboard_from_data(data)
                    if profile:
                        results["success"] += 1
                        results["imported"].append({"pin": pin, "name": name})
                        self.log(f"Imported {name} ({pin})")
                    else:
                        results["failed"] += 1
                        results["errors"].append(f"Row {row_num}: Onboarding failed for {pin}")
                except Exception as e:
                    results["failed"] += 1
                    results["errors"].append(f"Row {row_num}: {pin} — {str(e)}")

        self.log(f"=== BATCH IMPORT DONE: {results['success']} imported, {results['skipped']} skipped, {results['failed']} failed ===")
        return results

    def _row_to_data(self, row: dict) -> dict:
        """Convert CSV row to onboarding data dict."""
        data = {}

        # Required fields
        data["pin"] = row["pin"].upper()
        data["name"] = row["name"]
        data["business_type"] = row.get("business_type", "sole_proprietor")
        data["industry"] = row.get("industry", "retail_wholesale")
        data["turnover_bracket"] = row.get("turnover_bracket", "below_1m")

        # Optional fields with defaults
        data["business_name"] = row.get("business_name") or data["name"]
        data["county"] = row.get("county", "Nairobi")
        data["phone"] = row.get("phone", "")
        data["email"] = row.get("email") or None
        data["preferred_language"] = row.get("preferred_language", "en")
        data["preferred_channel"] = row.get("preferred_channel", "whatsapp")

        # Numeric fields
        try:
            data["annual_turnover_kes"] = float(row.get("annual_turnover_kes", 0))
        except ValueError:
            data["annual_turnover_kes"] = 0

        # Boolean fields
        data["has_employees"] = row.get("has_employees", "").lower() in ("true", "yes", "y", "1")
        data["is_vat_registered"] = row.get("is_vat_registered", "").lower() in ("true", "yes", "y", "1")
        data["has_etims"] = row.get("has_etims", "").lower() in ("true", "yes", "y", "1")

        try:
            data["employee_count"] = int(row.get("employee_count", 0)) if data["has_employees"] else 0
        except ValueError:
            data["employee_count"] = 0

        # Rental income
        rental = row.get("rental_income_annual_kes")
        data["rental_income_annual_kes"] = float(rental) if rental else None

        return data

    def generate_template(self, output_path: str | Path) -> Path:
        """Generate a blank CSV template for batch onboarding."""
        output_path = Path(output_path)
        all_fields = self.REQUIRED_FIELDS + list(self.OPTIONAL_FIELDS.keys())

        with open(output_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(all_fields)
            # Write one example row
            writer.writerow([
                "A123456789B", "Jane Wanjiru", "sole_proprietor", "food_hospitality",
                "1m_to_8m", "Jane's Kitchen", "Nairobi", "2500000",
                "true", "3", "false", "false",
                "0723456789", "jane@example.com", "en", "whatsapp", ""
            ])

        self.log(f"CSV template written to {output_path}")
        return output_path

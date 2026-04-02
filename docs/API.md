# KRA HELMET — API Documentation

Base URL: `http://localhost:8000`
Interactive docs: `http://localhost:8000/docs` (Swagger UI)

## Authentication

Protected endpoints require an API key via the `X-API-Key` header.

**Setup:**
1. Set `HELMET_API_KEY=your-secret-key` in your `.env` file
2. Pass the key in every request:

```bash
curl -H "X-API-Key: your-secret-key" http://localhost:8000/smes
```

**Auth disabled when:** no `HELMET_API_KEY` is set, or `HELMET_API_AUTH=false` in env.

Public endpoints (`/`, `/health`, `/dashboard`, `/guides`) do not require authentication.

---

## Endpoints

### System

#### `GET /`

Service info and available endpoints.

```bash
curl http://localhost:8000/
```

```json
{
  "service": "KRA HELMET",
  "version": "1.0.0",
  "status": "running",
  "auth_required": false,
  "endpoints": {
    "health": "/health",
    "smes": "/smes",
    "check": "/check/{pin}",
    "onboard": "POST /onboard",
    "filing": "POST /file/{pin}",
    "dashboard": "/dashboard",
    "report": "/report/{pin}",
    "audit": "/audit",
    "guides": "/guides"
  }
}
```

#### `GET /health`

System health check. Verifies config, SME registry, intelligence data, data directories, audit trail, and authentication status.

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "healthy",
  "timestamp": "2026-03-30T10:15:00.000000",
  "checks": {
    "config": {"status": "ok", "version": "1.0.0"},
    "sme_registry": {"status": "ok", "count": 3},
    "intelligence_data": {"status": "ok", "missing": []},
    "confirmed_profiles": {"status": "ok"},
    "processed_obligations": {"status": "ok"},
    "filings": {"status": "ok"},
    "staging": {"status": "ok"},
    "audit_trail": {"status": "ok"},
    "authentication": {"status": "disabled"}
  }
}
```

| Status | Meaning |
|---|---|
| `healthy` | All checks passed |
| `degraded` | One or more checks failed |

---

### SME Management

#### `GET /smes`

List all onboarded SMEs. **Requires auth.**

```bash
curl -H "X-API-Key: your-key" http://localhost:8000/smes
```

```json
{
  "count": 2,
  "smes": [
    {
      "pin": "A000000001B",
      "name": "Brian Ochieng",
      "business_name": "Ochieng Traders",
      "industry": "retail_wholesale"
    }
  ]
}
```

#### `GET /smes/{pin}`

Get full SME profile. **Requires auth.**

| Parameter | Type | Description |
|---|---|---|
| `pin` | path | KRA PIN (format: `A000000001B`) |

```bash
curl -H "X-API-Key: your-key" http://localhost:8000/smes/A000000001B
```

**Errors:**
- `400` — Invalid PIN format
- `404` — SME not found

#### `POST /onboard`

Onboard a new SME. **Requires auth.**

```bash
curl -X POST http://localhost:8000/onboard \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "pin": "A987654321Z",
    "name": "Jane Wanjiru",
    "business_name": "Wanjiru Consultants",
    "business_type": "sole_proprietor",
    "industry": "professional_services",
    "county": "Nairobi",
    "annual_turnover_kes": 3500000,
    "turnover_bracket": "1m_to_8m",
    "has_employees": true,
    "employee_count": 4,
    "is_vat_registered": false,
    "has_etims": true,
    "phone": "0712345678",
    "email": "jane@example.com",
    "preferred_language": "en",
    "preferred_channel": "whatsapp"
  }'
```

**Request body — `OnboardRequest`:**

| Field | Type | Required | Default | Validation |
|---|---|---|---|---|
| `pin` | string | Yes | — | KRA PIN: letter + 9 digits + letter (e.g. `A000000001B`) |
| `name` | string | Yes | — | Min 2 characters |
| `business_name` | string | No | same as `name` | — |
| `business_type` | string | No | `sole_proprietor` | `sole_proprietor`, `partnership`, `limited_company` |
| `industry` | string | No | `retail_wholesale` | See [Industries](#industries) |
| `county` | string | No | `Nairobi` | — |
| `annual_turnover_kes` | float | No | `0` | Must be >= 0 |
| `turnover_bracket` | string | No | `below_1m` | `below_1m`, `1m_to_8m`, `8m_to_25m`, `above_25m` |
| `has_employees` | bool | No | `false` | — |
| `employee_count` | int | No | `0` | — |
| `is_vat_registered` | bool | No | `false` | — |
| `has_etims` | bool | No | `false` | — |
| `phone` | string | No | `""` | Kenya format: `07XXXXXXXX` or `+2547XXXXXXXX` |
| `email` | string | No | `null` | — |
| `preferred_language` | string | No | `en` | `en` (English), `sw` (Swahili) |
| `preferred_channel` | string | No | `whatsapp` | `whatsapp`, `sms`, `email` |
| `rental_income_annual_kes` | float | No | `null` | — |

**Response:**

```json
{
  "status": "onboarded",
  "pin": "A987654321Z",
  "name": "Jane Wanjiru",
  "obligations": ["income_tax_resident", "tot", "paye", "nssf", "shif", "housing_levy"]
}
```

**Errors:**
- `400` — Validation error (invalid PIN, business_type, industry, etc.)
- `409` — SME already onboarded with that PIN
- `500` — Onboarding failed

---

### Compliance

#### `GET /check/{pin}`

Run full 9-step compliance check for an SME. Returns risk score, penalties, urgency, and a plain-language explanation. **Requires auth.**

| Parameter | Type | Description |
|---|---|---|
| `pin` | path | KRA PIN |

```bash
curl -H "X-API-Key: your-key" http://localhost:8000/check/A000000001B
```

```json
{
  "pin": "A000000001B",
  "name": "Brian Ochieng",
  "compliance": {
    "overall": "non_compliant",
    "overdue": ["tot", "vat"],
    "upcoming": ["paye"],
    "compliant": ["nssf"]
  },
  "risk": {
    "risk_score": 65,
    "risk_level": "high",
    "factors": {}
  },
  "penalties": {
    "total_exposure_kes": 45000,
    "severity": "manageable",
    "breakdown": []
  },
  "urgency": {
    "urgency_level": "high",
    "action_required": true
  },
  "obligations": [],
  "message": "You have 2 overdue tax obligations...",
  "alerts_queued": 1
}
```

**Errors:**
- `400` — Invalid PIN format
- `404` — SME not found or check failed

#### `GET /check`

Run compliance check for all onboarded SMEs. **Requires auth.**

```bash
curl -H "X-API-Key: your-key" http://localhost:8000/check
```

```json
{
  "checked": 3,
  "results": [
    {
      "pin": "A000000001B",
      "name": "Brian Ochieng",
      "compliance": "non_compliant",
      "risk_score": 65,
      "urgency": "high"
    }
  ]
}
```

---

### Filings

#### `POST /file/{pin}`

Record a tax filing for an SME. **Requires auth.**

| Parameter | Type | Description |
|---|---|---|
| `pin` | path | KRA PIN |

```bash
curl -X POST http://localhost:8000/file/A000000001B \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "tax_type": "vat",
    "period": "2026-03",
    "amount_kes": 125000,
    "reference": "ACK-2026-0345"
  }'
```

**Request body — `FilingRequest`:**

| Field | Type | Required | Default | Validation |
|---|---|---|---|---|
| `tax_type` | string | Yes | — | See [Tax Types](#tax-types) |
| `period` | string | Yes | — | `YYYY-MM` format (e.g. `2026-03`) |
| `amount_kes` | float | No | `0` | Must be >= 0 |
| `reference` | string | No | `""` | iTax acknowledgement number |

**Response:**

```json
{
  "status": "recorded",
  "filing": {
    "pin": "A000000001B",
    "tax_type": "vat",
    "period": "2026-03",
    "amount_kes": 125000,
    "reference": "ACK-2026-0345",
    "filed_at": "2026-03-30T10:30:00.000000"
  }
}
```

**Errors:**
- `400` — Invalid PIN, tax type, period, or amount
- `404` — SME not found

#### `GET /filings/{pin}`

Get filing history for an SME. **Requires auth.**

| Parameter | Type | In | Description |
|---|---|---|---|
| `pin` | string | path | KRA PIN |
| `tax_type` | string | query | Filter by tax type (optional) |

```bash
curl -H "X-API-Key: your-key" http://localhost:8000/filings/A000000001B
curl -H "X-API-Key: your-key" "http://localhost:8000/filings/A000000001B?tax_type=vat"
```

```json
{
  "pin": "A000000001B",
  "summary": {
    "total_filings": 5,
    "total_amount_kes": 380000,
    "tax_types_filed": ["vat", "paye", "tot"]
  },
  "filings": []
}
```

---

### Reports & Dashboard

#### `GET /dashboard`

Generate and serve the live HTML dashboard. **No auth required.** Returns HTML.

```bash
curl http://localhost:8000/dashboard
# Opens in browser: http://localhost:8000/dashboard
```

#### `GET /report/{pin}`

Generate a per-SME HTML compliance report. Print-ready. **Requires auth.** Returns HTML.

| Parameter | Type | Description |
|---|---|---|
| `pin` | path | KRA PIN |

```bash
curl -H "X-API-Key: your-key" http://localhost:8000/report/A000000001B
# Opens in browser: http://localhost:8000/report/A000000001B
```

**Errors:**
- `400` — Invalid PIN format
- `404` — SME not found

---

### Audit Trail

#### `GET /audit`

Get the immutable audit trail. **Requires auth.**

| Parameter | Type | In | Default | Description |
|---|---|---|---|---|
| `pin` | string | query | `null` | Filter by KRA PIN (optional) |
| `limit` | int | query | `50` | Max entries to return |

```bash
curl -H "X-API-Key: your-key" http://localhost:8000/audit
curl -H "X-API-Key: your-key" "http://localhost:8000/audit?pin=A000000001B&limit=10"
```

```json
{
  "count": 5,
  "entries": [
    {
      "timestamp": "2026-03-30T10:00:00.000000",
      "event": "COMPLIANCE_CHECK",
      "sme_pin": "A000000001B",
      "details": {}
    }
  ]
}
```

---

### Filing Guides

#### `GET /guides`

List all available iTax filing guides. **No auth required.**

```bash
curl http://localhost:8000/guides
```

```json
{
  "count": 11,
  "guides": [
    {"tax_key": "vat", "title": "How to File VAT on iTax"},
    {"tax_key": "paye", "title": "How to File PAYE on iTax"},
    {"tax_key": "tot", "title": "How to File Turnover Tax on iTax"}
  ]
}
```

#### `GET /guides/{tax_key}`

Get step-by-step filing instructions for a specific tax type. **No auth required.**

| Parameter | Type | Description |
|---|---|---|
| `tax_key` | path | Tax type key (e.g. `vat`, `paye`, `tot`) |

```bash
curl http://localhost:8000/guides/vat
```

```json
{
  "tax_key": "vat",
  "title": "How to File VAT on iTax",
  "itax_menu_path": "Returns > File Return > VAT",
  "estimated_time": "15-20 minutes",
  "steps": [
    "Log in to iTax at https://itax.kra.go.ke",
    "Navigate to Returns > File Return > VAT",
    "..."
  ],
  "documents_needed": ["Sales invoices", "Purchase invoices", "ETR Z-reports"],
  "common_mistakes": ["Filing after the 20th deadline"],
  "tips": ["Keep monthly summaries ready"]
}
```

**Errors:**
- `404` — Guide not found

---

## Error Responses

All errors return a consistent JSON format:

**Validation errors (400):**
```json
{
  "detail": "Invalid KRA PIN format: BADPIN"
}
```

**Authentication errors (401):**
```json
{
  "detail": "Invalid or missing API key. Set X-API-Key header."
}
```

**Not found (404):**
```json
{
  "detail": "SME not found: A000000001B"
}
```

**Conflict (409):**
```json
{
  "detail": "SME already onboarded: A000000001B"
}
```

**Server errors (500):**
```json
{
  "error": "ValueError",
  "detail": "Something went wrong",
  "timestamp": "2026-03-30T10:00:00.000000"
}
```

---

## Reference

### Industries

| Key | Description |
|---|---|
| `retail_wholesale` | Retail & Wholesale |
| `professional_services` | Professional Services |
| `food_hospitality` | Food & Hospitality |
| `transport` | Transport |
| `manufacturing` | Manufacturing |
| `rental_income` | Rental Income |
| `digital_online` | Digital / Online |
| `construction` | Construction |
| `agriculture` | Agriculture |
| `salon_beauty` | Salon & Beauty |
| `education` | Education |
| `healthcare` | Healthcare |

### Tax Types

| Key | Tax |
|---|---|
| `tot` | Turnover Tax |
| `vat` | Value Added Tax |
| `paye` | Pay As You Earn |
| `nssf` | NSSF Contributions |
| `shif` | Social Health Insurance Fund |
| `housing_levy` | Affordable Housing Levy |
| `income_tax_resident` | Income Tax (Resident Individual) |
| `income_tax_corporate` | Income Tax (Corporate) |
| `withholding_tax` | Withholding Tax |
| `mri` | Monthly Rental Income |
| `presumptive_tax` | Presumptive Tax |
| `excise_duty` | Excise Duty |

### KRA PIN Format

Pattern: `[A-Z][0-9]{9}[A-Z]` — one letter, nine digits, one letter.

Examples: `A000000001B`, `P051234567Q`, `A018542504L`

### Turnover Brackets

| Key | Range (KES) |
|---|---|
| `below_1m` | Under 1,000,000 |
| `1m_to_8m` | 1,000,000 – 8,000,000 |
| `8m_to_25m` | 8,000,000 – 25,000,000 |
| `above_25m` | Over 25,000,000 |

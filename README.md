# Insighta Labs — Intelligence Query Engine

A FastAPI service that stores demographic profiles and exposes a queryable API with advanced filtering, sorting, pagination, and natural language search.

## Endpoints

### `POST /api/profiles`
Create a profile from a name via Genderize / Agify / Nationalize. Idempotent — returns existing profile if name already exists.

**Request:**
```json
{ "name": "ella" }
```

**Response (201):**
```json
{
  "status": "success",
  "data": {
    "id": "019534a1-3b2c-7f4d-a1b2-c3d4e5f67890",
    "name": "ella",
    "gender": "female",
    "gender_probability": 0.99,
    "age": 46,
    "age_group": "adult",
    "country_id": "NG",
    "country_name": "Nigeria",
    "country_probability": 0.85,
    "created_at": "2026-04-01T12:00:00Z"
  }
}
```

---

### `GET /api/profiles`
List profiles with optional filtering, sorting, and pagination.

**Filter params:**

| Param | Type | Description |
|---|---|---|
| `gender` | string | `male` or `female` |
| `age_group` | string | `child`, `teenager`, `adult`, `senior` |
| `country_id` | string | ISO-2 code e.g. `NG` |
| `min_age` | int | minimum age (inclusive) |
| `max_age` | int | maximum age (inclusive) |
| `min_gender_probability` | float | 0.0–1.0 |
| `min_country_probability` | float | 0.0–1.0 |

**Sorting:**

| Param | Values |
|---|---|
| `sort_by` | `age`, `created_at`, `gender_probability` |
| `order` | `asc` (default), `desc` |

**Pagination:**

| Param | Default | Max |
|---|---|---|
| `page` | 1 | — |
| `limit` | 10 | 50 |

**Example:**
```
GET /api/profiles?gender=male&country_id=NG&min_age=25&sort_by=age&order=desc&page=1&limit=10
```

**Response (200):**
```json
{
  "status": "success",
  "page": 1,
  "limit": 10,
  "total": 2026,
  "data": [
    {
      "id": "b3f9c1e2-7d4a-4c91-9c2a-1f0a8e5b6d12",
      "name": "emmanuel okonkwo",
      "gender": "male",
      "gender_probability": 0.99,
      "age": 34,
      "age_group": "adult",
      "country_id": "NG",
      "country_name": "Nigeria",
      "country_probability": 0.85,
      "created_at": "2026-04-01T12:00:00Z"
    }
  ]
}
```

All filters are combinable. Every condition must match.

---

### `GET /api/profiles/search?q=<query>`
Natural language query endpoint. Converts plain English into filters then runs the same query pipeline as `GET /api/profiles`.

Supports `page` and `limit` pagination params.

**Examples:**
```
GET /api/profiles/search?q=young males from nigeria
GET /api/profiles/search?q=females above 30
GET /api/profiles/search?q=adult males from kenya
GET /api/profiles/search?q=people from angola
GET /api/profiles/search?q=male and female teenagers above 17
```

---

### `GET /api/profiles/{id}`
Get a single profile by UUID v7.

**Response (200):** Full profile object.

---

### `DELETE /api/profiles/{id}`
Delete a profile. Returns `204 No Content`.

---

## Natural Language Parsing

### How it works

The parser (`parse_query`) lowercases the query then applies a series of regex rules in order. Each rule extracts one filter dimension; all extracted filters are combined (AND logic) before hitting the database.

### Supported keywords and mappings

**Gender:**
| Keywords | Filter |
|---|---|
| male, males, man, men, boy, boys | `gender=male` |
| female, females, woman, women, girl, girls, lady, ladies | `gender=female` |
| both (e.g. "male and female") | no gender filter |

**Age groups (stored values):**
| Keywords | Filter |
|---|---|
| child, children, kid, kids | `age_group=child` |
| teenager, teenagers, teen, teens, adolescent | `age_group=teenager` |
| adult, adults | `age_group=adult` |
| senior, seniors, elderly | `age_group=senior` |

**Special age keyword:**
| Keyword | Filter |
|---|---|
| young | `min_age=16` + `max_age=24` (parsing only — not a stored group) |

**Age modifiers:**
| Pattern | Filter |
|---|---|
| above N / over N / older than N / at least N | `min_age=N` |
| below N / under N / younger than N / at most N | `max_age=N` |
| between N and M | `min_age=N` + `max_age=M` |
| ages N to M | `min_age=N` + `max_age=M` |

**Country:**
Recognized after `from` or `in`. Uses longest-match against a dictionary of ~100 country names and demonyms (e.g. "nigerian" → `NG`, "south africa" → `ZA`).

| Pattern | Filter |
|---|---|
| from nigeria / nigerian | `country_id=NG` |
| from kenya / kenyan | `country_id=KE` |
| from angola | `country_id=AO` |
| in south africa | `country_id=ZA` |
| (see source for full list) | |

**Rule: uninterpretable query** — if no filter is extracted, returns:
```json
{ "status": "error", "message": "Unable to interpret query" }
```

### Limitations

- **No synonym expansion.** "guys" or "dudes" are not recognized as male.
- **No relative age words beyond "young".** "middle-aged", "old", "teenage" are not mapped (use `age_group=adult` or explicit age ranges).
- **Country detection is dictionary-based.** Misspellings, abbreviations outside the dictionary (e.g. "naija"), or uncommon country names will not be recognized.
- **Single-country extraction.** Only one country per query is extracted; "from nigeria or kenya" will only match "nigeria".
- **No negation.** "not from nigeria" is not supported.
- **No OR logic.** Each extracted filter is applied with AND. "adults or seniors" returns neither.
- **"Young" overrides explicit age group.** If "young" appears with a stored age group word (child/teen/adult/senior), the stored age group takes precedence.
- **Ambiguous "in".** "in adults" might incorrectly trigger country detection if "adults" were a country name — it isn't, but novel queries with coincidental matches may behave unexpectedly.

---

## Error Responses

```json
{ "status": "error", "message": "<description>" }
```

| Status | Reason |
|---|---|
| 400 | Missing or empty parameter |
| 404 | Profile not found |
| 422 | Invalid parameter type or value; unable to interpret NL query |
| 500 | Internal server error |
| 502 | External API (Genderize / Agify / Nationalize) returned an invalid response |

---

## Classification Rules

- **Age group**: `0–12` → child, `13–19` → teenager, `20–59` → adult, `60+` → senior
- **Nationality**: country with highest probability from Nationalize API
- **IDs**: UUID v7 (time-ordered)
- **Timestamps**: UTC ISO 8601 (`YYYY-MM-DDTHH:MM:SSZ`)

---

## Database Setup (Vercel + Neon)

Vercel is serverless — SQLite doesn't persist between invocations. Use a hosted PostgreSQL database such as [Neon](https://neon.tech) (free tier).

1. Create a Neon project and copy the connection string (`postgresql://...?sslmode=require`).
2. In Vercel → **Settings → Environment Variables** → add `DATABASE_URL`.
3. Deploy. The table and indexes are created automatically on cold start.

### Seeding

```bash
pip install -r requirements.txt
python3 seed.py
```

The seed script generates 2026 profiles and inserts them. Re-running is safe — existing names are skipped.

---

## Local Development

```bash
pip install -r requirements.txt
uvicorn api.index:app --reload
```

SQLite is used automatically at `/tmp/profiles.db` when `DATABASE_URL` is unset.

```bash
# Seed locally
python3 seed.py

# Query
curl "http://localhost:8000/api/profiles?gender=male&country_id=NG&min_age=25&sort_by=age&order=desc"
curl "http://localhost:8000/api/profiles/search?q=young+males+from+nigeria"
```

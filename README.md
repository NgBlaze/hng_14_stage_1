# Profile Enrichment API

A FastAPI service that accepts a name, enriches it with data from three external APIs (Genderize, Agify, Nationalize), stores the result in a PostgreSQL database, and exposes CRUD endpoints.

## Endpoints

### `POST /api/profiles`
Create a profile for a name. If the name already exists, returns the existing profile.

**Request body:**
```json
{ "name": "ella" }
```

**Response (201 Created):**
```json
{
  "status": "success",
  "data": {
    "id": "019534a1-3b2c-7f4d-a1b2-c3d4e5f67890",
    "name": "ella",
    "gender": "female",
    "gender_probability": 0.99,
    "sample_size": 1234,
    "age": 46,
    "age_group": "adult",
    "country_id": "DRC",
    "country_probability": 0.85,
    "created_at": "2026-04-01T12:00:00Z"
  }
}
```

**Response if name already exists (200):**
```json
{
  "status": "success",
  "message": "Profile already exists",
  "data": { ...existing profile... }
}
```

---

### `GET /api/profiles`
List all profiles. Supports optional case-insensitive query filters.

**Query params:** `gender`, `country_id`, `age_group`

**Example:** `GET /api/profiles?gender=male&country_id=NG`

**Response (200):**
```json
{
  "status": "success",
  "count": 2,
  "data": [
    { "id": "...", "name": "emmanuel", "gender": "male", "age": 25, "age_group": "adult", "country_id": "NG" }
  ]
}
```

---

### `GET /api/profiles/{id}`
Get a single profile by UUID.

**Response (200):** Full profile object (same structure as POST response).

---

### `DELETE /api/profiles/{id}`
Delete a profile. Returns `204 No Content` on success.

---

## Error Responses

All errors follow:
```json
{ "status": "error", "message": "<description>" }
```

| Status | Reason |
|--------|--------|
| 400 | Missing or empty `name` |
| 404 | Profile not found |
| 422 | `name` is not a string |
| 500 | Internal server error |
| 502 | External API (Genderize / Agify / Nationalize) returned an invalid response |

---

## Classification Rules

- **Age group** (from Agify): `0–12` → child, `13–19` → teenager, `20–59` → adult, `60+` → senior
- **Nationality**: country with the highest probability from Nationalize
- **IDs**: UUID v7 (time-ordered)
- **Timestamps**: UTC ISO 8601

---

## Database Setup (Vercel Deployment)

Vercel is serverless — SQLite doesn't persist between invocations. You need a hosted PostgreSQL database. [Neon](https://neon.tech) has a free tier and integrates directly with Vercel.

**Steps:**

1. Sign up at [neon.tech](https://neon.tech) → create a new project → copy the connection string.
   It looks like: `postgresql://user:password@host/dbname?sslmode=require`

2. In your Vercel project → **Settings → Environment Variables** → add:
   ```
   DATABASE_URL = postgresql://user:password@host/dbname?sslmode=require
   ```

3. Deploy (or redeploy). The table is created automatically on first cold start.

> **Note:** If your connection string starts with `postgres://` (Heroku format), the app converts it to `postgresql://` automatically.

---

## Local Development

```bash
pip install -r requirements.txt
uvicorn api.index:app --reload
```

For local dev, a SQLite file is used automatically at `/tmp/profiles.db` (no setup needed).

To use PostgreSQL locally:
```bash
export DATABASE_URL=postgresql://user:password@localhost/profiles
uvicorn api.index:app --reload
```

Test endpoints:
```bash
# Create
curl -X POST http://localhost:8000/api/profiles \
  -H "Content-Type: application/json" \
  -d '{"name": "ella"}'

# List
curl http://localhost:8000/api/profiles

# Get single
curl http://localhost:8000/api/profiles/<id>

# Delete
curl -X DELETE http://localhost:8000/api/profiles/<id>
```

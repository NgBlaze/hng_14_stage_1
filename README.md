# Name Gender Classifier API

A FastAPI service that classifies names by gender using the [Genderize.io](https://genderize.io) API.

## Endpoint

### `GET /api/classify?name={name}`

Returns gender classification data for a given name.

**Success Response (200)**
```json
{
  "status": "success",
  "data": {
    "name": "john",
    "gender": "male",
    "probability": 0.99,
    "sample_size": 1234,
    "is_confident": true,
    "processed_at": "2026-04-01T12:00:00Z"
  }
}
```

**Error Responses**
| Status | Reason |
|--------|--------|
| 400 | Missing or empty `name` parameter |
| 422 | `name` is not a valid string |
| 500 | Internal server error |
| 502 | Upstream API unreachable or failed |

All errors follow:
```json
{ "status": "error", "message": "<description>" }
```

## Logic

- `sample_size` = `count` from Genderize API
- `is_confident` = `true` when `probability >= 0.7` **AND** `sample_size >= 100`
- `processed_at` = current UTC time in ISO 8601 format, generated per request
- If Genderize returns `gender: null` or `count: 0`, returns an error response

## Local Development

```bash
pip install -r requirements.txt
uvicorn api.index:app --reload
```

Then visit: `http://localhost:8000/api/classify?name=john`

## Deployment

Deployed on [Vercel](https://vercel.com). Pushes to `main` trigger automatic redeployment.
# hng_14_stage_0

Backend Wizards — Stage 0 Task: API Integration & Data Processing Assessment

Stage 0 is live. :dart:

Build a single GET endpoint that integrates with an external API and returns a processed response.

Task details in Airtable: link
Explainer video: link: link

What it should do

Call the Genderize API using a name query parameter, process the raw response, and return a structured result.

Processing rules:
- Extract gender, probability, and count from the API response. Rename count to sample_size
- Compute is_confident: true when probability >= 0.7 AND sample_size >= 100. Both conditions must pass. If either fails, it's false
- Generate processed_at on every request. UTC, ISO 8601. Not hardcoded

The endpoint you're building

1. Classify Name
GET /api/classify?name={name}

Success Response (200 OK):
 json
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

Error Responses:
- 400 Bad Request: Missing or empty name parameter
- 422 Unprocessable Entity: name is not a string
- 500/502: Upstream or server failure

All errors follow this structure:
 json
 { "status": "error", "message": "<error message>" }

Genderize edge cases:
If the response comes back with gender: null or count: 0, return:
 json
 { "status": "error", "message": "No prediction available for the provided name" }

Additional requirements:
- CORS header: Access-Control-Allow-Origin: *. Without this, the grading script cannot reach your server
- Response time under 500ms, excluding external API latency
- The endpoint must handle multiple requests without going down

Evaluation Criteria
- Endpoint Availability — 10 points
- Query Parameter Handling — 10 points
- External API Integration — 20 points
- Data Extraction Accuracy — 15 points
- Confidence Logic — 15 points
- Error Handling — 10 points
- Edge Case Handling — 10 points
- Response Format & Structure — 10 points
- Total — 100 points

Submission instructions
- Any language works
- Render is not accepted. Vercel, Railway, Heroku, AWS, PXXL App, and similar platforms are fine
- The GitHub repo should include:
  - A clear README
- Test your endpoint before submitting. Confirm it returns the correct response format
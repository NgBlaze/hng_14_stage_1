# Insighta Labs+ — Backend API

Secure, role-based profile intelligence API built with FastAPI, PostgreSQL (Neon), and deployed on Vercel.

**Live API:** https://hng-14-stage-1.vercel.app  
**Docs (Swagger):** https://hng-14-stage-1.vercel.app/docs

---

## System Architecture

```
┌──────────────────────────────────────────────────────────┐
│                        Clients                           │
│   CLI (insighta)      Web Portal       Direct API        │
└──────────┬───────────────┬────────────────┬─────────────┘
           │               │                │
           │  Bearer JWT   │  HTTP-only     │  Bearer JWT
           │               │  cookies       │
           ▼               ▼                ▼
┌──────────────────────────────────────────────────────────┐
│             FastAPI  (Vercel Serverless)                  │
│                                                          │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────────┐  │
│  │  /auth/*     │  │ /api/profiles │  │  Middleware  │  │
│  │  OAuth + JWT │  │  CRUD + NLP   │  │  CORS, Rate  │  │
│  └──────────────┘  └───────────────┘  │  Limit, Log  │  │
│                                       └──────────────┘  │
└───────────────────────────┬──────────────────────────────┘
                            │
           ┌────────────────┴──────────────────┐
           ▼                                   ▼
┌─────────────────────┐            ┌────────────────────────┐
│   Neon PostgreSQL   │            │    External APIs        │
│   - profiles        │            │    - genderize.io       │
│   - users           │            │    - agify.io           │
│   - refresh_tokens  │            │    - nationalize.io     │
│   - oauth_states    │            └────────────────────────┘
└─────────────────────┘
```

### Module Layout

```
api/
├── index.py          # FastAPI app, CORS, middleware, exception handlers
├── auth.py           # JWT helpers, PKCE verify, get_current_user, check_api_version
├── limiter.py        # Slowapi rate limiter keyed by user ID or IP
├── models.py         # SQLAlchemy models: Profile, User, RefreshToken, OAuthState
├── database.py       # Engine, SessionLocal, init_db (auto-migrations)
├── services.py       # Business logic: create / list / search / delete profiles
├── nlp.py            # Natural language query parser
├── utils.py          # UUID v7 generator, age classifier, country lookup table
└── routes/
    ├── auth.py       # All /auth/* endpoints
    └── profiles.py   # All /api/profiles/* endpoints
```

---

## Authentication Flow

### Web Portal (Browser OAuth)

```
Browser                    Backend                    GitHub
   │                          │                          │
   │── GET /auth/github ──────►│                          │
   │◄── 302 → GitHub ─────────│                          │
   │                          │                          │
   │── authenticates ─────────────────────────────────►│
   │◄── redirect /auth/github/callback?code= ───────────│
   │                          │                          │
   │                          │── POST access_token ────►│
   │                          │◄── gh_token ─────────────│
   │                          │── GET /user, /emails ───►│
   │                          │◄── user info ────────────│
   │                          │                          │
   │                          │  upsert user in DB       │
   │                          │  issue JWT pair          │
   │◄── 302 → /dashboard ─────│                          │
   │    Set-Cookie: access_token  (HttpOnly; Secure)     │
   │    Set-Cookie: refresh_token (HttpOnly; Secure)     │
   │    Set-Cookie: csrf_token    (Secure; JS-readable)  │
```

### CLI (PKCE Flow)

```
CLI                         Backend                    GitHub
 │                             │                          │
 │  code_verifier = base64url(random_bytes(32))           │
 │  code_challenge = base64url(SHA-256(code_verifier))    │
 │                             │                          │
 │  start local HTTP server (random port)                 │
 │  open browser → GitHub OAuth URL                       │
 │◄── GET /callback?code=... (local server captures it)   │
 │                             │                          │
 │── POST /auth/github/exchange ──────────────────────►  │
 │   { code, code_verifier,    │                          │
 │     code_challenge,         │                          │
 │     redirect_uri }          │                          │
 │                             │  verify PKCE challenge   │
 │                             │  exchange code → gh token│
 │                             │  upsert user             │
 │                             │  issue JWT pair          │
 │◄── { access_token,          │                          │
 │      refresh_token, user }  │                          │
 │                             │                          │
 │  save to ~/.insighta/credentials.json (chmod 600)      │
```

### PKCE Verification

```python
# CLI generates
code_verifier  = base64url(os.urandom(32))
code_challenge = base64url(hashlib.sha256(code_verifier).digest())

# Backend verifies
expected = base64url(hashlib.sha256(code_verifier).digest())
assert expected == code_challenge   # if mismatch → 400
```

---

## Token Handling

| Token | Expiry | Web storage | CLI storage | Transport |
|---|---|---|---|---|
| Access | 3 min | `HttpOnly` cookie | `~/.insighta/credentials.json` | `Authorization: Bearer` or cookie |
| Refresh | 5 min | `HttpOnly` cookie | `~/.insighta/credentials.json` | Request body or cookie |

**Rotation:** every `/auth/refresh` call revokes the presented token instantly and issues a new pair. Raw tokens are never stored — only SHA-256 hashes are persisted in the `refresh_tokens` table.

**Refresh flow:**
1. Client makes a request → `401 Unauthorized`
2. Client sends refresh token to `POST /auth/refresh`
3. Backend verifies hash, checks expiry, marks token revoked
4. Backend issues new access + refresh pair
5. Client retries original request with new access token
6. If refresh also fails → user must log in again

---

## Role Enforcement

| Role | Permissions |
|---|---|
| `admin` | Read, create, delete profiles |
| `analyst` | Read and search only |

Admin usernames are configured via `ADMIN_GITHUB_USERNAMES` (comma-separated). Role is assigned at first login and re-evaluated on every subsequent login.

Enforcement uses FastAPI dependency injection — no scattered checks inside route handlers:

```python
# Require any authenticated user
user = Depends(get_current_user)

# Require admin role
user = Depends(require_admin)
```

`is_active = False` on a user → `403 Forbidden` on all requests regardless of role.

---

## API Versioning

All `/api/profiles/*` endpoints require the header:

```
X-API-Version: 1
```

Missing or incorrect value → `400 Bad Request`. Browser-navigable endpoints (CSV export) additionally accept `?api_version=1` as a query parameter fallback since browsers cannot set custom headers on direct URL navigation.

---

## Natural Language Search

`GET /api/profiles/search?q=<query>`

Regex-based parser in `api/nlp.py` — no external ML dependencies.

**Supported patterns:**

| Query fragment | Extracted filter |
|---|---|
| `male`, `men`, `boys` | `gender=male` |
| `female`, `women`, `girls` | `gender=female` |
| `children`, `kids` | `age_group=child` |
| `teenagers`, `teens` | `age_group=teenager` |
| `adults` | `age_group=adult` |
| `seniors`, `elderly` | `age_group=senior` |
| `young` | `min_age=16, max_age=24` |
| `above 30`, `over 30`, `older than 30` | `min_age=30` |
| `below 50`, `under 50` | `max_age=50` |
| `between 20 and 40` | `min_age=20, max_age=40` |
| `from Nigeria`, `in Germany` | `country_id=NG / DE` |

Country names and demonyms (e.g. "Nigerian", "British") are resolved to ISO 3166-1 alpha-2 codes via a static lookup table covering 90+ countries.

**Examples:**
```
"young males from Nigeria"     → gender=male, min_age=16, max_age=24, country_id=NG
"adult women in Germany"       → gender=female, age_group=adult, country_id=DE
"seniors above 60"             → age_group=senior, min_age=60
"teenagers between 13 and 17" → age_group=teenager, min_age=13, max_age=17
```

---

## Rate Limiting

| Scope | Limit |
|---|---|
| `/auth/*` endpoints | 10 requests / minute |
| All other endpoints | 60 requests / minute per user |

Authenticated requests are keyed by user ID extracted from the JWT; unauthenticated requests fall back to client IP. Exceeded limits return `429 Too Many Requests`.

---

## Endpoints Reference

### Auth

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/auth/github` | — | Initiate GitHub OAuth (web portal) |
| `GET` | `/auth/github/callback` | — | OAuth callback handler |
| `POST` | `/auth/github/exchange` | — | CLI PKCE code exchange |
| `POST` | `/auth/refresh` | — | Rotate access + refresh token pair |
| `POST` | `/auth/logout` | — | Revoke refresh token |
| `GET` | `/auth/whoami` | Required | Return current user details |

### Profiles

| Method | Path | Role | Description |
|---|---|---|---|
| `GET` | `/api/profiles` | Any | List with filters, sorting, pagination |
| `GET` | `/api/profiles/search` | Any | Natural language search |
| `GET` | `/api/profiles/export` | Any | Download CSV with same filters |
| `GET` | `/api/profiles/{id}` | Any | Fetch a single profile |
| `POST` | `/api/profiles` | Admin | Create profile from external APIs |
| `DELETE` | `/api/profiles/{id}` | Admin | Delete a profile |

All profile endpoints require `X-API-Version: 1`.

---

## Paginated Response Format

```json
{
  "status": "success",
  "page": 1,
  "limit": 10,
  "total": 2034,
  "total_pages": 204,
  "links": {
    "self": "/api/profiles?page=1&limit=10",
    "next": "/api/profiles?page=2&limit=10",
    "prev": null
  },
  "data": [ ... ]
}
```

---

## Environment Variables

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `GITHUB_CLIENT_ID` | GitHub OAuth App client ID |
| `GITHUB_CLIENT_SECRET` | GitHub OAuth App client secret |
| `JWT_SECRET_KEY` | Secret for HS256 JWT signing |
| `ADMIN_GITHUB_USERNAMES` | Comma-separated admin GitHub usernames |
| `BACKEND_URL` | Public URL of this API |
| `WEB_PORTAL_URL` | Public URL of the web portal |

---

## Local Development

```bash
git clone https://github.com/NgBlaze/hng_14_stage_1.git
cd hng_14_stage_1
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in values
uvicorn api.index:app --reload
# → http://localhost:8000
```

---

## Deployment

Deployed on Vercel as a Python serverless function. All requests are rewritten to `api/index.py` via `vercel.json`.

```bash
vercel --prod
```

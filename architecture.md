# Insighta Labs+ — Architecture

A FastAPI-based profile intelligence API. Users authenticate via GitHub OAuth (web cookie or CLI PKCE); admins create demographic profiles by name (enriched via 3 external APIs) and analysts read/search them. Deployed as a Vercel serverless function backed by Neon PostgreSQL.

---

## 1. High-Level Component Diagram

```mermaid
graph LR
    CLIENTS[Clients<br/>Web · CLI · Direct API]
    API[Insighta API<br/>FastAPI on Vercel]
    DB[(PostgreSQL<br/>Neon)]
    REDIS[(Redis<br/>cache)]
    GH[GitHub<br/>OAuth + Identity]
    DEMO[Demographics APIs<br/>genderize · agify · nationalize]

    CLIENTS -->|HTTPS| API
    API --> REDIS
    API --> DB
    API --> GH
    API --> DEMO
```

| Component | Role |
|---|---|
| **Clients** | Web (cookie + CSRF), CLI (Bearer + PKCE), direct API |
| **Insighta API** | Stateless FastAPI app — auth, authorization, profile CRUD, NLP search |
| **Redis** | Read-through cache for `GET /api/profiles` and `/search`; invalidated on writes. Optional — falls back to DB if `REDIS_URL` is unset |
| **PostgreSQL** | Single source of truth: users, profiles, refresh tokens, oauth states |
| **GitHub** | OAuth identity provider |
| **Demographics APIs** | External enrichment to build profiles from a name |

---

## 2. Actors & Authorization

```mermaid
flowchart LR
    ANON((Anonymous))
    ANALYST((Analyst))
    ADMIN((Admin))
    API[[Insighta API]]

    ANON -->|/auth/*| API
    ANALYST -->|read · search · export| API
    ADMIN -->|read + create + delete| API
```

Every protected request runs through: **identity** (JWT or cookie) → **role** (`require_admin` on writes) → **CSRF** (cookie writes only) → **API version** (`X-API-Version: 1`) → **rate limit** (10/min on `/auth/*`, 60/min on `/api/*`).

---

## 3. Sequence — Web Portal OAuth Login

```mermaid
sequenceDiagram
    participant U as Browser
    participant API
    participant GH as GitHub
    participant DB

    U->>API: GET /auth/github
    API->>DB: store oauth_state + PKCE
    API-->>U: 302 → GitHub authorize

    U->>GH: authenticate
    GH-->>U: 302 → /auth/github/callback?code&state

    U->>API: GET /auth/github/callback
    API->>GH: exchange code → gh_token
    API->>GH: GET /user, /user/emails
    API->>DB: upsert user · insert refresh_token (hashed)
    API-->>U: 302 → /dashboard<br/>Set-Cookie: access · refresh · csrf
```

---

## 4. Sequence — CLI Login (PKCE)

```mermaid
sequenceDiagram
    participant CLI
    participant Browser
    participant API
    participant GH as GitHub

    CLI->>CLI: generate PKCE pair
    CLI->>Browser: open GitHub authorize URL
    Browser->>GH: authenticate
    GH-->>Browser: redirect → localhost?code
    Browser->>CLI: deliver code

    CLI->>API: POST /auth/github/exchange (code + verifier)
    API->>API: verify PKCE
    API->>GH: exchange code · fetch user
    API-->>CLI: { access_token, refresh_token, user }
```

---

## 5. Sequence — Admin Creates a Profile

```mermaid
sequenceDiagram
    participant C as Admin
    participant API
    participant SVC as Profile Service
    participant EXT as Demographics APIs
    participant DB

    C->>API: POST /api/profiles { name }
    API->>API: auth · role · CSRF · version · rate limit
    API->>SVC: create_profile_from_name(name)
    SVC->>DB: SELECT existing
    alt new name
        SVC->>EXT: parallel fetch (gender, age, nationality)
        SVC->>DB: INSERT profile
        SVC-->>API: 201
    else exists
        SVC-->>API: 200
    end
    API-->>C: response
```

---

## 6. Sequence — Natural-Language Search (cached)

```mermaid
sequenceDiagram
    participant C as Client
    participant API
    participant R as Redis
    participant NLP
    participant DB

    C->>API: GET /api/profiles/search?q=...
    API->>R: GET cache key
    alt cache hit
        R-->>API: payload
    else miss
        API->>NLP: parse_query(q)
        API->>DB: SELECT WHERE filters
        API->>R: SETEX (60s)
    end
    API-->>C: paginated results
```

---

## 7. Sequence — Refresh-Token Rotation

```mermaid
sequenceDiagram
    participant C as Client
    participant API
    participant DB

    C->>API: POST /auth/refresh
    API->>DB: lookup token (sha256), check expiry
    API->>DB: revoke presented · insert new
    API-->>C: new access + refresh + csrf
```

---

## 8. Data Model

```mermaid
erDiagram
    USERS ||--o{ REFRESH_TOKENS : owns
    USERS {
        string id PK
        string github_id UK
        string username
        string role
        bool is_active
    }
    REFRESH_TOKENS {
        string id PK
        string user_id FK
        string token_hash UK
        datetime expires_at
        bool is_revoked
    }
    OAUTH_STATES {
        string state UK
        string code_verifier
        string source
        bool used
    }
    PROFILES {
        string id PK
        string name UK
        string gender
        int age
        string age_group
        string country_id
    }
```

---

## 9. Deployment

```mermaid
graph LR
    FN[FastAPI on Vercel<br/>api/index.py]
    FN --> NEON[(Neon PostgreSQL)]
    FN --> REDIS[(Redis Cloud)]
    FN --> GH[GitHub]
    FN --> DEMO[Demographics APIs]
```

Single-region, stateless serverless function. Durable state in Neon; ephemeral cache in Redis. No background workers — every workflow is request-scoped.

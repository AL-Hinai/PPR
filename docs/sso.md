# Single sign-on and the API

## Single sign-on for staff (OpenID Connect)

Reviewers and the Head of Department can sign in with their Ministry account instead of a PPR password, through
any OpenID Connect provider: Microsoft Entra ID (Azure AD), ADFS 2016 or later, Keycloak and others. Company
applicants keep PPR passwords.

How it behaves:

- Accounts are still issued in PPR (Django admin). A provider login only signs in an **existing, active reviewer
  or Head of Department whose email matches** the provider's `email` claim (or `upn` / `preferred_username`).
  No account is created from the provider (`OIDC_CREATE_USER = False`).
- Roles and review specialties stay in PPR.
- Password sign-in keeps working for everyone, so an administrator can still sign in if the provider is down.

### What Ministry IT provides

Register PPR as a web application (confidential client) with:

- Redirect URI: `https://<ppr host>/oidc/callback/`
- Scopes: `openid email profile`
- Signing algorithm: RS256

Then set these in `.env` (values from the provider's `/.well-known/openid-configuration`) and reload:

```bash
OIDC_RP_CLIENT_ID=...
OIDC_RP_CLIENT_SECRET=...
OIDC_OP_AUTHORIZATION_ENDPOINT=https://login.microsoftonline.com/<tenant>/oauth2/v2.0/authorize
OIDC_OP_TOKEN_ENDPOINT=https://login.microsoftonline.com/<tenant>/oauth2/v2.0/token
OIDC_OP_USER_ENDPOINT=https://graph.microsoft.com/oidc/userinfo
OIDC_OP_JWKS_ENDPOINT=https://login.microsoftonline.com/<tenant>/discovery/v2.0/keys
# Optional: SSO_LABEL="Sign in with MOH account"
```

The login page then shows a "Sign in with your Ministry account" button. Setting `OIDC_RP_CLIENT_ID` is what
switches it on. On a free PythonAnywhere account, the provider's hosts must be on the outbound allow-list.

## Read-only API for other systems

Other Ministry systems (a product register, pharmacovigilance, import permits) can read application status and
decisions. The API is read-only and never returns documents, assessments or notes.

Issue a key per system (it is printed once; only a hash is stored), and switch keys off in Django admin
(*API keys*):

```bash
python manage.py create_api_key "Drug register"
```

Requests send the key as a bearer token:

```bash
curl -H "Authorization: Bearer ppr_..." https://<ppr host>/api/v1/applications/?status=APPROVED
```

| Endpoint | Returns |
|---|---|
| `GET /api/v1/applications/` | Applications except drafts, newest change first, 100 per page. Filters: `status`, `updated_since` (ISO 8601), `page` |
| `GET /api/v1/applications/<reference_no>/` | One application with its sequences (number, validation status, GCC submission type and unit) |

Each item has the reference number, product, active ingredients, strength, dosage form, ATC code, application
type, status, company, submission and update times, and the decision (outcome, approval number, valid until).

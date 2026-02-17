# Configuration Directory

This directory contains configuration files for the SpendSense application.

## credentials.json (Local Development)

For local development, you can create a `credentials.json` file here with your Google OAuth credentials:

```json
{
  "installed": {
    "client_id": "your-client-id.apps.googleusercontent.com",
    "project_id": "your-project-id",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_secret": "your-client-secret",
    "redirect_uris": ["http://localhost"]
  }
}
```

## Environment Variables (Production)

For production deployments (Docker, cloud platforms), use environment variables instead:

```bash
export GOOGLE_CLIENT_ID="your-client-id.apps.googleusercontent.com"
export GOOGLE_CLIENT_SECRET="your-client-secret"
export GOOGLE_PROJECT_ID="your-project-id"
export FLASK_SECRET_KEY="your-random-secret-key"
```

Or use a `.env` file in the project root (see `.env.example`).

## Getting OAuth Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Create a new project or select an existing one
3. Enable the Gmail API
4. Create OAuth 2.0 credentials:
   - Application type: **Desktop app** (for local development)
   - Or **Web application** (for production deployment)
5. Download the credentials JSON file
6. Either:
   - Save it as `config/credentials.json`
   - Or extract the client_id and client_secret and set as environment variables

## Security Notes

- **Never commit `credentials.json` to git** - it's in `.gitignore`
- **Never commit `.env` files** - they're in `.gitignore`
- Use environment variables for production deployments
- Rotate your credentials if they're ever exposed

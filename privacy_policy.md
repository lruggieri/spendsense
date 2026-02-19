## Introduction

This Privacy Policy describes how SpendSense ("we", "our", or "the application") collects, uses, and protects your personal information when you use our expense tracking and classification service.

## Information We Collect

### 1. Google Account Information
When you sign in using Google OAuth, we collect:
- Your email address
- Your Google account ID
- Access tokens for Gmail API (if you choose to fetch transactions from Gmail)

### 2. Gmail Data
If you choose to use the Gmail transaction fetching feature, we access:
- Email messages from specific financial service providers (banks, payment services)
- Email content to extract transaction information (date, amount, description)
- This data is processed locally and stored in your application database

### 3. Transaction Data
We store:
- Transaction details (date, amount, description, source)
- Manual category assignments you create
- Comments you add to transactions
- Classification metadata (how each transaction was categorized)

### 4. Usage Data
- Session information (stored in the application database)
- OAuth tokens (encrypted and stored for API access)

## How We Use Your Information

We use the collected information to:
1. **Authenticate your access** - Verify your identity using Google OAuth
2. **Fetch transactions** - Retrieve transaction emails from your Gmail account
3. **Categorize expenses** - Automatically classify transactions using regex patterns and machine learning
4. **Generate regex patterns** - Optionally use Google Gemini API to generate classification rules from email content
5. **Provide analysis** - Generate expense reports, charts, and trends
6. **Maintain your preferences** - Store manual category assignments and comments

## Data Storage and Security

### Local Storage
- All data is stored locally in the application database
- The application runs on a private server
- No data is transmitted to external servers except as described in the Third-Party Services section below

### Encryption at Rest
Sensitive fields are encrypted in the database using **AES-256-GCM**:
- Transaction descriptions
- Transaction comments
- OAuth tokens

Encryption details:
- **Envelope encryption**: a per-installation Data Encryption Key (DEK) is wrapped with a Key Encryption Key (KEK) following RFC 3394 key-wrapping
- A 12-byte random nonce is prepended to each encrypted value
- `transaction_amount` is stored in plaintext (required for aggregation queries)
- An `encryption_version` column tracks whether each row uses plaintext (`0`) or AES-256-GCM (`1`)
- If decryption is unavailable (e.g. missing key), affected fields display as `[Encrypted]` rather than causing errors

### Security Measures
- Google OAuth 2.0 for secure authentication
- Session-based access control with 7-day session expiration
- Session cookies set with `HttpOnly` and `SameSite=Lax` flags; `Secure` flag enabled in production
- Access token refresh mechanism to minimize token exposure
- Optional `ALLOWED_EMAILS` environment variable to restrict access to authorized accounts only

## Third-Party Services

### Google Services
We use the following Google services:
- **Google OAuth 2.0** - For user authentication
- **Gmail API** - To fetch transaction emails (only when you explicitly initiate a fetch)
- **Google Gemini API** (`gemini-flash-latest`) - Optionally used to generate regex classification patterns from email text; this is an optional feature that sends email body content to the Gemini API only when explicitly triggered

Google's use of information received from Gmail APIs will adhere to the [Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy), including the Limited Use requirements.

### European Central Bank (ECB)
The application may download daily currency exchange rate tables from the European Central Bank's public data feed. **No personal data is transmitted to the ECB** — only publicly available rate tables are downloaded.

### Data Sharing
We do **NOT**:
- Sell your data to third parties
- Share your data with advertisers
- Transfer personal data to external services beyond what is described above (Google OAuth, Gmail API, Gemini API when explicitly used)
- Use your data for purposes other than providing the expense tracking service

## Gmail API Scope and Usage

### Limited Use Disclosure
Our use of information received from Google APIs adheres to the [Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy#additional_requirements_for_specific_api_scopes), including the Limited Use requirements.

### Scopes Used
The application requests the following Gmail API scope:
- `https://www.googleapis.com/auth/gmail.readonly` - Read-only access to Gmail messages

### How We Use Gmail Data
Gmail data is used exclusively to:
1. Search for transaction emails from specific financial service providers
2. Extract transaction information (date, amount, merchant name)
3. Store extracted transaction data in the application database
4. No Gmail content is shared with any third party
5. Gmail access occurs only when you explicitly trigger a transaction fetch

## Your Rights and Choices

You have the right to:
1. **Access your data** - Review all stored transactions and categories through the web interface
2. **Modify your data** - Edit transaction categories, add comments, and create manual entries
3. **Revoke access** - Disconnect the application from your Google account at any time via [Google Account Permissions](https://myaccount.google.com/permissions)

## Data Retention

- Transaction data is retained indefinitely unless you manually delete it
- Session data expires after 7 days
- You can delete all data by removing the application database file

## Changes to This Privacy Policy

We may update this Privacy Policy from time to time. Changes will be reflected by updating the "Last Updated" date at the top of this policy. Continued use of the application after changes constitutes acceptance of the updated policy.

## Compliance

This application:
- Complies with Google OAuth 2.0 requirements
- Follows Gmail API Terms of Service
- Adheres to the Google API Services User Data Policy, including Limited Use requirements

## Contact Information

If you have questions about this Privacy Policy or how your data is handled, please contact:

**Email:** luc4.ruggieri@gmail.com
**Website:** https://github.com/lruggieri/spendsense

## Open Source

This application is open source. You can review the code to understand exactly how your data is processed:
**Repository:** https://github.com/lruggieri/spendsense


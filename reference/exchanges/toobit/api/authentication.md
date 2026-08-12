# Authentication

Learn how to authenticate your API requests.

## API Keys

API keys are the primary method of authentication. Each API key is associated with your account and can be managed from your dashboard.

### Obtaining an API Key

  1. Log in to your account
  2. Navigate to Settings > API Keys
  3. Click "Create New API Key"
  4. Give your key a descriptive name
  5. Copy and securely store your API key

DANGER

API keys provide full access to your account. Keep them secure and never expose them in client-side code or public repositories.

### Using API Keys

Include your API key in the `Authorization` header of every request:

http
```
Authorization: Bearer YOUR_API_KEY
```

1

### Example Request

bash
```
curl -X GET https://api.example.com/v1/users/usr_123 \
  -H "Authorization: Bearer sk_live_abc123xyz789"
```

1
2

## Token Types

We support two types of API keys:

### Test Keys

  * Prefix: `sk_test_`
  * Use for development and testing
  * No charges are made
  * Data is not persisted

### Live Keys

  * Prefix: `sk_live_`
  * Use in production
  * Real transactions and data
  * Secured with additional monitoring

## Best Practices

### 1\. Keep Keys Secret

Never expose API keys in:

  * Client-side code (JavaScript, mobile apps)
  * Public repositories (GitHub, GitLab)
  * Public forums or support tickets

### 2\. Use Environment Variables

Store API keys in environment variables:

bash
```
# .env file
API_KEY=sk_live_abc123xyz789
```

1
2

javascript
```
// JavaScript
const apiKey = process.env.API_KEY;
```

1
2

python
```
# Python
import os
api_key = os.environ.get('API_KEY')
```

1
2
3

### 3\. Rotate Keys Regularly

  * Rotate API keys every 90 days
  * Immediately rotate if a key is compromised
  * Use multiple keys for different services

### 4\. Use Key Restrictions

Restrict API keys by:

  * IP address
  * Referrer URL
  * Specific API endpoints

## Key Management

### Listing API Keys

bash
```
GET /v1/api-keys
```

1

Response:

json
```
{
  "success": true,
  "data": [
    {
      "id": "key_123",
      "name": "Production Key",
      "prefix": "sk_live_",
      "created_at": "2025-01-01T00:00:00Z",
      "last_used": "2025-01-15T10:30:00Z"
    }
  ]
}
```

1
2
3
4
5
6
7
8
9
10
11
12

### Revoking an API Key

bash
```
DELETE /v1/api-keys/key_123
```

1

Response:

json
```
{
  "success": true,
  "message": "API key revoked successfully"
}
```

1
2
3
4

## OAuth 2.0 (Coming Soon)

We're working on OAuth 2.0 support for third-party integrations. This will allow:

  * User-authorized access
  * Granular permission scopes
  * Refresh tokens
  * Improved security for client applications

Stay tuned for updates!

## Troubleshooting

### 401 Unauthorized

**Problem** : Missing or invalid API key

**Solution** : Verify your API key is correct and included in the Authorization header

### 403 Forbidden

**Problem** : API key doesn't have permission for this resource

**Solution** : Check your API key permissions in the dashboard

### Key Not Working

  1. Verify the key hasn't been revoked
  2. Check for typos in the key
  3. Ensure you're using the correct environment (test vs. live)
  4. Contact support if issues persist

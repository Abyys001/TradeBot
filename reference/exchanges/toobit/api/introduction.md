# Introduction

## API Key Setup

  * Some endpoints will require an API Key. Please refer to this page  regarding API key creation.
  * Once API key is created, it is recommended to set IP restrictions on the key for security reasons.
  * **Never share your API key/secret key to ANYONE.**

WARNING

If the API keys were accidentally shared, please delete them immediately and create a new key.

API Usage Notice

To help maintain platform stability, clients must implement appropriate retry backoff and rate limiting after failed requests. A high volume of repeated failed or invalid requests from the same IP within a short period, including but not limited to HTTP `404` and `429`, may be classified as abnormal traffic and may result in a temporary IP ban or access restriction.

After receiving HTTP `429`, immediately reduce the request rate and retry only after the time indicated by the `X-Api-Limit-Reset-Timestamp` response header. For HTTP `404` and other errors, verify and correct the request URL, parameters, or calling method before retrying, and avoid immediate repeated requests.

## API Key Restrictions

  * After creating the API key, the default restrictions is `Enable Reading`.

## Enabling Accounts

### Spot Account

A `SPOT` account is provided by default upon creation of a Account.

### USDT-M Account

Users can enable USDT-M account as needed.

# Card Payment Idempotency

## Why idempotency
Network timeouts do not mean the acquirer did not process the authorization. A request that timed out may already have been approved and the customer may already have been charged.

## Rule
Each business payment (one `transactionId`) must have exactly one idempotency key. The same key must be sent on every retry attempt of that payment. The acquirer returns the original result for a repeated key instead of creating a second authorization.

## Retry policy
- Retry only on timeouts and HTTP 5xx responses.
- At most 2 attempts.
- Generate the idempotency key once, before the first attempt, or derive it from the `transactionId`.

## Known risk
Generating a new key inside the retry loop causes duplicate charges when the first attempt timed out on the client side but succeeded at the acquirer.

# Coding Standards

## General
- Java 17, Spring Boot, constructor injection only.
- Keep validation logic in dedicated validator classes; services orchestrate.
- Public behaviour changes require a unit test (JUnit 5) that reproduces the original defect.

## Logging
- Always log the transaction id as `txn=<id>`.
- Never log full IBANs, card numbers or national identity numbers. Log only the last four characters if needed.

## Error codes
- Use the codes from the shared error code catalog. Do not invent new codes in a fix without registering them.

## Retries
- Retries must be idempotent. Reuse the same idempotency key for all attempts of one business operation.

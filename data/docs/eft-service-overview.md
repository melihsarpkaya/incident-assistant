# EFT Service Overview

## Purpose
The eft-service sends domestic money transfers (EFT) to the clearing house. Branch, mobile and internet banking channels call the same REST endpoint `POST /api/v1/eft/transfers`.

## Request flow
1. `EftTransferController` receives the request.
2. `EftTransferService` validates the beneficiary IBAN with `IbanValidator`.
3. If the IBAN is invalid the transfer is rejected with error code `EFT-4042` and nothing is sent to clearing.
4. `BeneficiaryClient` verifies the beneficiary name with the beneficiary registry.
5. The transfer is sent to clearing.

## Channels
Mobile and internet banking clients send IBANs without spaces. The branch teller screen sends the IBAN exactly as typed by the teller, which is usually the printed format with spaces every four characters.

## Logs
Logs are written to `eft-service.log`. The transaction id is added to every line through the logging MDC as `txn=<id>`, including lines written by helper components such as `IbanValidator`. IBANs must never be written to logs in clear text.

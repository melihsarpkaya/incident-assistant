# IBAN Validation Rules

## Normalization
Before any validation step, an IBAN must be normalized:
- remove all whitespace characters (spaces, tabs, non-breaking spaces),
- convert letters to upper case.
Customers and tellers commonly use the printed format `TR18 0006 2001 1900 0006 6723 15`. This format is valid input and must be accepted after normalization.

## Length and country
A Turkish IBAN starts with `TR` and is exactly 26 characters long after normalization.

## Checksum
The checksum follows ISO 13616 (mod 97). Move the first four characters to the end, replace letters with numbers (A=10 ... Z=35) and check that the remainder of division by 97 is 1.

## Error handling
An IBAN that fails normalization, length or checksum validation is rejected with `EFT-4042`. The rejection reason must be logged without the full IBAN.

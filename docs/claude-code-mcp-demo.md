# Claude Code + bank-knowledge MCP demo

Recorded on 2026-10-29 with Claude Code 2.1.312. Claude Code was restricted to the `bank-knowledge` MCP server (all built-in file tools disabled), so every fact below came through the same MCP tools the incident agent uses.

```bash
claude -p "<prompt>" --strict-mcp-config --mcp-config .mcp.json \
  --allowedTools "mcp__bank-knowledge__*" --disallowedTools "Edit,Write,Bash,Read,Glob,Grep"
```

## Prompt

> Incident INC-1001: branch EFT transfers fail with EFT-4042 when the IBAN is typed with spaces. Use ONLY the bank-knowledge MCP tools (search_logs, search_code, read_file, search_docs, lookup_error_code) and the docs://coding-standards resource if available. Find the defect and propose the fix as a unified diff for the Java source plus a JUnit 5 test that reproduces the defect. Do not modify any files. Cite the refs you used.

## MCP calls made by Claude Code

- `mcp__bank-knowledge__lookup_error_code` `{"code": "EFT-4042"}`
- `mcp__bank-knowledge__search_logs` `{"query": "EFT-4042", "service": "eft-service"}`
- `mcp__bank-knowledge__search_docs` `{"query": "IBAN validation spaces normalization"}`
- `ReadMcpResourceTool` `{"server": "bank-knowledge", "uri": "docs://coding-standards"}`
- `mcp__bank-knowledge__search_code` `{"query": "IbanValidator", "service": "eft-service"}`
- `mcp__bank-knowledge__search_logs` `{"query": "TX-20261028-0412"}`
- `mcp__bank-knowledge__read_file` `{"path": "eft-service/src/main/java/com/demobank/eft/IbanValidator.java"}`
- `mcp__bank-knowledge__read_file` `{"path": "eft-service/src/main/java/com/demobank/eft/EftTransferService.java"}`
- `mcp__bank-knowledge__search_logs` `{"query": "TX-20261028-0413"}`
- `mcp__bank-knowledge__search_code` `{"query": "BeneficiaryClient verify", "service": "eft-service"}`

## Answer (unedited)

## INC-1001: the IBAN validator doesn't strip spaces before checking the IBAN

The diff and test below haven't been compiled or run, and no files were changed. I checked by hand that the test IBAN `TR180006200119000006672315` passes mod-97: the remainder is 1. Running the test against the current code should still be done to confirm it fails before the fix.

**Defect:** `IbanValidator.isValid()` checks the length and checksum on the raw input. It never removes whitespace or converts to upper case first.

**How it fails:**
1. EFT-4042 belongs to `IbanValidator` and means "Beneficiary IBAN failed validation before clearing" (`catalog:EFT-4042`).
2. Both failing transactions came from the BRANCH channel. In each one the validator logged `IBAN format check failed length=32` just before the EFT-4042 rejection (`log:eft-service.log:3-5`, `log:eft-service.log:6-8`).
3. 32 is the 26-character Turkish IBAN plus the 6 spaces of the printed format `TR18 0006 2001 1900 0006 6723 15`.
4. The rules say an IBAN must have all whitespace (including non-breaking spaces) removed and be upper-cased before any validation step, and that the printed format is valid input (`doc:iban-rules.md#normalization`). A Turkish IBAN is 26 characters after that step (`doc:iban-rules.md#length-and-country`).
5. The code compares `iban.length()` to 26 on the raw string and computes the checksum on the raw string too (`code:eft-service/src/main/java/com/demobank/eft/IbanValidator.java:18`, `:22`, `:26`).

**A second problem nearby:** `EftTransferService` sends the raw, un-normalized IBAN to `BeneficiaryClient.verify` (`code:eft-service/src/main/java/com/demobank/eft/EftTransferService.java:28`). Once validation accepts spaced IBANs, the spaced form would go downstream unless the service passes on the normalized value. The diff fixes that as well.

### Proposed fix

```diff
--- a/eft-service/src/main/java/com/demobank/eft/IbanValidator.java
+++ b/eft-service/src/main/java/com/demobank/eft/IbanValidator.java
@@ -1,6 +1,8 @@
 package com.demobank.eft;
 
 import java.math.BigInteger;
+import java.util.Locale;
+import java.util.regex.Pattern;
 import org.slf4j.Logger;
 import org.slf4j.LoggerFactory;
 import org.springframework.stereotype.Component;
@@ -10,14 +12,24 @@ public class IbanValidator {
 
     private static final Logger log = LoggerFactory.getLogger(IbanValidator.class);
     private static final int TR_IBAN_LENGTH = 26;
+    // \s alone misses non-breaking spaces (U+00A0, U+202F); \p{Z} covers them.
+    private static final Pattern WHITESPACE = Pattern.compile("[\\s\\p{Z}]+");
+
+    public String normalize(String iban) {
+        if (iban == null) {
+            return null;
+        }
+        return WHITESPACE.matcher(iban).replaceAll("").toUpperCase(Locale.ROOT);
+    }
 
     public boolean isValid(String iban) {
-        if (iban == null) {
+        String normalized = normalize(iban);
+        if (normalized == null) {
             return false;
         }
-        if (!iban.startsWith("TR") || iban.length() != TR_IBAN_LENGTH) {
-            log.debug("IBAN format check failed length={}", iban.length());
+        if (!normalized.startsWith("TR") || normalized.length() != TR_IBAN_LENGTH) {
+            log.debug("IBAN format check failed length={}", normalized.length());
             return false;
         }
-        return checksumMatches(iban);
+        return checksumMatches(normalized);
     }
--- a/eft-service/src/main/java/com/demobank/eft/EftTransferService.java
+++ b/eft-service/src/main/java/com/demobank/eft/EftTransferService.java
@@ -20,12 +20,13 @@ public class EftTransferService {
     public TransferResult transfer(TransferRequest request) {
         log.info("EFT request received txn={} channel={}", request.transactionId(), request.channel());
 
-        if (!ibanValidator.isValid(request.beneficiaryIban())) {
+        String beneficiaryIban = ibanValidator.normalize(request.beneficiaryIban());
+        if (!ibanValidator.isValid(beneficiaryIban)) {
             log.warn("EFT-4042 beneficiary IBAN rejected txn={}", request.transactionId());
             return TransferResult.rejected(request.transactionId(), "EFT-4042", "Beneficiary IBAN invalid");
         }
 
-        beneficiaryClient.verify(request.beneficiaryIban(), request.beneficiaryName());
+        beneficiaryClient.verify(beneficiaryIban, request.beneficiaryName());
         log.info("EFT sent to clearing txn={}", request.transactionId());
         return TransferResult.accepted(request.transactionId());
     }
```

**Design choices:**
- **Upper-casing with `Locale.ROOT`:** under a Turkish default locale, `"i".toUpperCase()` gives `İ` (dotted capital I), which would break a lowercase IBAN containing "i". `Locale.ROOT` avoids that, and the test covers it.
- **Normalizing inside the validator:** the coding standards say validation logic belongs in validator classes and services only orchestrate (`docs://coding-standards`). So `normalize()` lives in `IbanValidator` and the service just calls it.
- **Logging and error codes unchanged:** the log still records only the length, never the IBAN, which follows the logging rule (`docs://coding-standards`, `doc:iban-rules.md#error-handling`). No new error code is added.

### JUnit 5 test (new file `eft-service/src/test/java/com/demobank/eft/IbanValidatorTest.java`)

```java
package com.demobank.eft;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Locale;
import org.junit.jupiter.api.Test;

class IbanValidatorTest {

    private static final String COMPACT_IBAN = "TR180006200119000006672315";
    private static final String PRINTED_IBAN = "TR18 0006 2001 1900 0006 6723 15";

    private final IbanValidator validator = new IbanValidator();

    @Test
    void acceptsCompactIban() {
        assertTrue(validator.isValid(COMPACT_IBAN));
    }

    // INC-1001: branch input in printed format was rejected with EFT-4042 (length=32).
    @Test
    void acceptsIbanTypedWithSpaces() {
        assertTrue(validator.isValid(PRINTED_IBAN));
    }

    @Test
    void acceptsIbanWithTabsAndNonBreakingSpaces() {
        assertTrue(validator.isValid("TR18\t0006\u00A02001 1900\u202F0006 6723 15 "));
    }

    @Test
    void acceptsLowerCaseIbanUnderTurkishLocale() {
        Locale original = Locale.getDefault();
        try {
            Locale.setDefault(Locale.forLanguageTag("tr-TR"));
            assertTrue(validator.isValid("tr18 0006 2001 1900 0006 6723 15"));
        } finally {
            Locale.setDefault(original);
        }
    }

    @Test
    void normalizeStripsWhitespaceAndUpperCases() {
        assertEquals(COMPACT_IBAN, validator.normalize("tr18 0006 2001 1900 0006 6723 15"));
    }

    @Test
    void stillRejectsSpacedIbanWithBadChecksum() {
        assertFalse(validator.isValid("TR19 0006 2001 1900 0006 6723 15"));
    }

    @Test
    void stillRejectsWrongLengthAndNull() {
        assertFalse(validator.isValid("TR18 0006 2001 1900 0006 6723"));
        assertFalse(validator.isValid(null));
    }
}
```

`acceptsIbanTypedWithSpaces` is the test that reproduces INC-1001. On the current code it should fail because the raw length is 32; with the fix it should pass.

**Still open:** an IBAN containing punctuation (for example `TR18-0006-…`) that happens to be 26 characters long would make `new BigInteger(...)` throw `NumberFormatException` instead of returning a clean EFT-4042. It's outside this incident, but a follow-up could check for letters and digits only before the checksum.

### Refs used
- `catalog:EFT-4042`
- `log:eft-service.log:3`, `:4`, `:5`, `:6`, `:7`, `:8`
- `doc:iban-rules.md#normalization`, `#length-and-country`, `#checksum`, `#error-handling`
- `docs://coding-standards`
- `code:eft-service/src/main/java/com/demobank/eft/IbanValidator.java:12-31`
- `code:eft-service/src/main/java/com/demobank/eft/EftTransferService.java:20-30`
- `code:eft-service/src/main/java/com/demobank/eft/BeneficiaryClient.java:15`

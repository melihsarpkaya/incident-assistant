package com.demobank.eft;

import java.math.BigInteger;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class IbanValidator {

    private static final Logger log = LoggerFactory.getLogger(IbanValidator.class);
    private static final int TR_IBAN_LENGTH = 26;

    public boolean isValid(String iban) {
        if (iban == null) {
            return false;
        }
        if (!iban.startsWith("TR") || iban.length() != TR_IBAN_LENGTH) {
            log.debug("IBAN format check failed length={}", iban.length());
            return false;
        }
        return checksumMatches(iban);
    }

    private boolean checksumMatches(String iban) {
        String rearranged = iban.substring(4) + iban.substring(0, 4);
        StringBuilder numeric = new StringBuilder();
        for (char c : rearranged.toCharArray()) {
            numeric.append(Character.isLetter(c) ? String.valueOf(c - 'A' + 10) : c);
        }
        return new BigInteger(numeric.toString()).mod(BigInteger.valueOf(97)).intValue() == 1;
    }
}

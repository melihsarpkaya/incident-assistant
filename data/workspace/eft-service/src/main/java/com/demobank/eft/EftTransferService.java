package com.demobank.eft;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class EftTransferService {

    private static final Logger log = LoggerFactory.getLogger(EftTransferService.class);

    private final IbanValidator ibanValidator;
    private final BeneficiaryClient beneficiaryClient;

    public EftTransferService(IbanValidator ibanValidator, BeneficiaryClient beneficiaryClient) {
        this.ibanValidator = ibanValidator;
        this.beneficiaryClient = beneficiaryClient;
    }

    public TransferResult transfer(TransferRequest request) {
        log.info("EFT request received txn={} channel={}", request.transactionId(), request.channel());

        if (!ibanValidator.isValid(request.beneficiaryIban())) {
            log.warn("EFT-4042 beneficiary IBAN rejected txn={}", request.transactionId());
            return TransferResult.rejected(request.transactionId(), "EFT-4042", "Beneficiary IBAN invalid");
        }

        beneficiaryClient.verify(request.beneficiaryIban(), request.beneficiaryName());
        log.info("EFT sent to clearing txn={}", request.transactionId());
        return TransferResult.accepted(request.transactionId());
    }
}

package com.demobank.card;

import java.net.SocketTimeoutException;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class PaymentRetryHandler {

    private static final Logger log = LoggerFactory.getLogger(PaymentRetryHandler.class);
    private static final int MAX_ATTEMPTS = 2;

    private final AcquirerClient acquirerClient;

    public PaymentRetryHandler(AcquirerClient acquirerClient) {
        this.acquirerClient = acquirerClient;
    }

    public PaymentResult executeWithRetry(PaymentRequest request) {
        for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
            String idempotencyKey = UUID.randomUUID().toString();
            try {
                log.info("Sending authorization txn={} attempt={} idempotencyKey={}",
                        request.transactionId(), attempt, idempotencyKey);
                return acquirerClient.authorize(request, idempotencyKey);
            } catch (SocketTimeoutException e) {
                log.warn("Acquirer timeout txn={} attempt={}", request.transactionId(), attempt);
            }
        }
        return PaymentResult.failed(request.transactionId(), "CRD-5030");
    }
}

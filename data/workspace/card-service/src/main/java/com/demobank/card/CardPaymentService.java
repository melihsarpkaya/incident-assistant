package com.demobank.card;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class CardPaymentService {

    private static final Logger log = LoggerFactory.getLogger(CardPaymentService.class);

    private final PaymentRetryHandler retryHandler;

    public CardPaymentService(PaymentRetryHandler retryHandler) {
        this.retryHandler = retryHandler;
    }

    public PaymentResult pay(PaymentRequest request) {
        log.info("Card payment started txn={} merchant={}", request.transactionId(), request.merchantId());
        PaymentResult result = retryHandler.executeWithRetry(request);
        log.info("Card payment finished txn={} status={}", request.transactionId(), result.status());
        return result;
    }
}

package com.demobank.card;

import java.net.SocketTimeoutException;
import org.springframework.stereotype.Component;

@Component
public class AcquirerClient {

    private final AcquirerGateway gateway;

    public AcquirerClient(AcquirerGateway gateway) {
        this.gateway = gateway;
    }

    /**
     * Sends an authorization to the acquirer. The acquirer deduplicates requests
     * only when the same Idempotency-Key header is sent again.
     */
    public PaymentResult authorize(PaymentRequest request, String idempotencyKey) throws SocketTimeoutException {
        return gateway.post("/authorizations", request, idempotencyKey);
    }
}

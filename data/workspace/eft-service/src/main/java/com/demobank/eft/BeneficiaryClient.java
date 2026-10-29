package com.demobank.eft;

import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class BeneficiaryClient {

    private final RestClient restClient;

    public BeneficiaryClient(RestClient beneficiaryRestClient) {
        this.restClient = beneficiaryRestClient;
    }

    public void verify(String iban, String beneficiaryName) {
        restClient.post()
                .uri("/beneficiaries/verify")
                .body(new BeneficiaryCheck(iban, beneficiaryName))
                .retrieve()
                .toBodilessEntity();
    }

    record BeneficiaryCheck(String iban, String name) {
    }
}

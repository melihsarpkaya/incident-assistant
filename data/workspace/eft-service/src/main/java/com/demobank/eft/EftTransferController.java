package com.demobank.eft;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class EftTransferController {

    private final EftTransferService transferService;

    public EftTransferController(EftTransferService transferService) {
        this.transferService = transferService;
    }

    @PostMapping("/api/v1/eft/transfers")
    public ResponseEntity<TransferResult> transfer(@RequestBody TransferRequest request) {
        return ResponseEntity.ok(transferService.transfer(request));
    }
}

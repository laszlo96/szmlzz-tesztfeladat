package com.example.imageprocessor.kafka;

import java.util.UUID;

public record ImageJobMessage(
        UUID jobId,
        String filename,
        byte[] imageData
) {}

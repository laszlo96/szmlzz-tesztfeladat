package com.example.imageprocessor.model;

import jakarta.persistence.*;
import lombok.Data;
import java.time.LocalDateTime;
import java.util.UUID;

@Data
@Entity
@Table(name = "image_jobs")
public class ImageJob {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    private String filename;
    private String s3Key;

    @Enumerated(EnumType.STRING)
    private JobStatus status;

    private LocalDateTime createdAt;
    private LocalDateTime processedAt;
    private String errorMessage;

    public enum JobStatus {
        PENDING, PROCESSING, DONE, FAILED
    }
}

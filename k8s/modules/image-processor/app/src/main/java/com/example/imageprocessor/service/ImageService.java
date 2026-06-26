package com.example.imageprocessor.service;

import com.example.imageprocessor.kafka.ImageJobMessage;
import com.example.imageprocessor.model.ImageJob;
import com.example.imageprocessor.repository.ImageJobRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

import java.time.LocalDateTime;
import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class ImageService {

    private final ImageJobRepository repository;
    private final S3Client s3Client;

    @Value("${app.s3.bucket}")
    private String bucket;

    public void process(ImageJobMessage message) {
        ImageJob job = repository.findById(message.jobId())
                .orElseThrow(() -> new IllegalArgumentException("Job not found: " + message.jobId()));

        job.setStatus(ImageJob.JobStatus.PROCESSING);
        repository.save(job);

        try {
            String s3Key = "images/" + message.jobId() + "/" + message.filename();
            s3Client.putObject(
                    PutObjectRequest.builder()
                            .bucket(bucket)
                            .key(s3Key)
                            .contentType("image/jpeg")
                            .build(),
                    RequestBody.fromBytes(message.imageData())
            );

            job.setS3Key(s3Key);
            job.setStatus(ImageJob.JobStatus.DONE);
            job.setProcessedAt(LocalDateTime.now());
            repository.save(job);

            log.info("Job {} processed, stored at s3://{}/{}", message.jobId(), bucket, s3Key);
        } catch (Exception e) {
            log.error("Job {} failed: {}", message.jobId(), e.getMessage());
            job.setStatus(ImageJob.JobStatus.FAILED);
            job.setErrorMessage(e.getMessage());
            repository.save(job);
        }
    }

    @Cacheable(value = "jobs", key = "#id")
    public ImageJob getJob(UUID id) {
        return repository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("Job not found: " + id));
    }
}

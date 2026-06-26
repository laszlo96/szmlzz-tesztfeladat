package com.example.imageprocessor.repository;

import com.example.imageprocessor.model.ImageJob;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.UUID;

public interface ImageJobRepository extends JpaRepository<ImageJob, UUID> {
}

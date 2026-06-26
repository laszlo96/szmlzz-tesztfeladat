package com.example.imageprocessor.controller;

import com.example.imageprocessor.model.ImageJob;
import com.example.imageprocessor.service.ImageService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.UUID;

@RestController
@RequestMapping("/api/jobs")
@RequiredArgsConstructor
public class ImageJobController {

    private final ImageService imageService;

    @GetMapping("/{id}")
    public ResponseEntity<ImageJob> getJob(@PathVariable UUID id) {
        return ResponseEntity.ok(imageService.getJob(id));
    }
}

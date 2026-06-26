package com.example.imageprocessor.kafka;

import com.example.imageprocessor.service.ImageService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Slf4j
@Component
@RequiredArgsConstructor
public class ImageJobConsumer {

    private final ImageService imageService;

    @KafkaListener(topics = "${app.kafka.topic}", groupId = "${app.kafka.group-id}")
    public void consume(ImageJobMessage message) {
        log.info("Received image job: {}", message.jobId());
        imageService.process(message);
    }
}

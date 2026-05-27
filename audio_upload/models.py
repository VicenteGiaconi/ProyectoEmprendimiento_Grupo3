from django.db import models


class AudioFile(models.Model):
    file = models.FileField(upload_to='audio/')
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    size_bytes = models.PositiveIntegerField()
    uploaded_at = models.DateTimeField(auto_now_add=True)
    transcription = models.TextField(blank=True, default='')
    transcription_status = models.CharField(
        max_length=20,
        choices=[('pending', 'Pending'), ('completed', 'Completed'), ('failed', 'Failed')],
        default='pending',
    )
    diarization = models.JSONField(default=list, blank=True)
    sentiment = models.JSONField(default=dict, blank=True)
    detected_language = models.CharField(max_length=20, blank=True, default='')

    def __str__(self):
        return self.original_name

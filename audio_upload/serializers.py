import os
from rest_framework import serializers
from django.conf import settings
from .models import AudioFile

EXTENSION_TO_MIME = {
    '.mp3': 'audio/mpeg',
    '.wav': 'audio/wav',
    '.ogg': 'audio/ogg',
    '.mp4': 'audio/mp4',
    '.m4a': 'audio/mp4',
    '.webm': 'audio/webm',
}


class AudioFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = AudioFile
        fields = ['id', 'original_name', 'content_type', 'size_bytes', 'uploaded_at', 'file', 'transcription', 'transcription_status', 'detected_language', 'diarization', 'sentiment']
        read_only_fields = ['id', 'original_name', 'content_type', 'size_bytes', 'uploaded_at', 'transcription', 'transcription_status', 'detected_language', 'diarization', 'sentiment']

    def validate_file(self, value):
        content_type = value.content_type

        # Normaliza tipos no-estándar usando la extensión del archivo.
        # Cubre: curl sin --type (octet-stream), Firefox/Safari con mp3 (audio/mp3),
        # y variantes de WAV (audio/x-wav, audio/vnd.wave).
        if content_type not in settings.ALLOWED_AUDIO_TYPES:
            ext = os.path.splitext(value.name)[1].lower()
            content_type = EXTENSION_TO_MIME.get(ext, content_type)
            value.content_type = content_type

        if content_type not in settings.ALLOWED_AUDIO_TYPES:
            raise serializers.ValidationError(
                f"Tipo de archivo no permitido: {content_type}. "
                f"Tipos aceptados: {', '.join(settings.ALLOWED_AUDIO_TYPES)}"
            )

        max_bytes = settings.MAX_AUDIO_SIZE_MB * 1024 * 1024
        if value.size > max_bytes:
            raise serializers.ValidationError(
                f"El archivo excede el tamaño máximo de {settings.MAX_AUDIO_SIZE_MB} MB."
            )

        return value

    def create(self, validated_data):
        file = validated_data['file']
        return AudioFile.objects.create(
            file=file,
            original_name=file.name,
            content_type=file.content_type,
            size_bytes=file.size,
        )

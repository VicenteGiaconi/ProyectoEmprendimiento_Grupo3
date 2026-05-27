from rest_framework import serializers
from django.conf import settings
from .models import AudioFile


class AudioFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = AudioFile
        fields = ['id', 'original_name', 'content_type', 'size_bytes', 'uploaded_at', 'file']
        read_only_fields = ['id', 'original_name', 'content_type', 'size_bytes', 'uploaded_at']

    def validate_file(self, value):
        content_type = value.content_type
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

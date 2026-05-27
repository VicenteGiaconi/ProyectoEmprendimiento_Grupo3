from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AudioFile
from .serializers import AudioFileSerializer
from .services import transcribe_audio


class AudioUploadView(APIView):
    parser_classes = [MultiPartParser]

    def post(self, request):
        serializer = AudioFileSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        audio = serializer.save()

        language = request.data.get('language') or None
        try:
            result = transcribe_audio(audio.file.path, language=language)
            audio.transcription = result['transcript']
            audio.diarization = result['diarization']
            audio.sentiment = result['sentiment']
            audio.detected_language = result.get('detected_language') or ''
            audio.transcription_status = 'completed'
        except Exception:
            audio.transcription_status = 'failed'

        audio.save(update_fields=['transcription', 'transcription_status', 'diarization', 'sentiment', 'detected_language'])

        return Response(AudioFileSerializer(audio).data, status=status.HTTP_201_CREATED)


class AudioListView(APIView):
    def get(self, request):
        audios = AudioFile.objects.order_by('-uploaded_at')
        serializer = AudioFileSerializer(audios, many=True)
        return Response(serializer.data)

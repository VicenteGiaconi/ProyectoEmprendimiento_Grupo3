from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AudioFile
from .serializers import AudioFileSerializer


class AudioUploadView(APIView):
    parser_classes = [MultiPartParser]

    def post(self, request):
        serializer = AudioFileSerializer(data=request.data)
        if serializer.is_valid():
            audio = serializer.save()
            return Response(AudioFileSerializer(audio).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AudioListView(APIView):
    def get(self, request):
        audios = AudioFile.objects.order_by('-uploaded_at')
        serializer = AudioFileSerializer(audios, many=True)
        return Response(serializer.data)

from django.shortcuts import render, redirect, get_object_or_404
from .forms import AudioFileUploadForm
from analytics.pipeline import run_pipeline
from audio_upload.models import AudioFile 

def upload_audio(request):
    if request.method == 'POST':
        form = AudioFileUploadForm(request.POST, request.FILES)
        if form.is_valid():
            audio_file = form.save()
            run_pipeline()  # Ejecutar el pipeline de análisis
            return redirect('dashboard')
    else:
        form = AudioFileUploadForm()
    return render(request, 'upload.html', {'form': form})

def dashboard(request):
    audios = AudioFile.objects.order_by('-uploaded_at')
    return render(request, 'dashboard.html', {'audios': audios})

def detail(request, audio_file_id):
    audio_file = get_object_or_404(AudioFile, id=audio_file_id)
    return render(request, 'detail.html', {'audio_file': audio_file})
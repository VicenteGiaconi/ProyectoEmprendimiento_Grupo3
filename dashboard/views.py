from django.shortcuts import render, redirect
from .forms import AudioFileUploadForm
from analytics.pipeline import run_pipeline

def upload_audio(request):
    if request.method == 'POST':
        form = AudioFileUploadForm(request.POST, request.FILES)
        if form.is_valid():
            audio_file = form.save()
            run_pipeline()  # Ejecutar el pipeline de análisis
            return redirect('dashboard')
    else:
        form = AudioFileUploadForm()
    return render(request, 'dashboard/upload.html', {'form': form})

def dashboard(request):
    return render(request, 'dashboards/base.html')

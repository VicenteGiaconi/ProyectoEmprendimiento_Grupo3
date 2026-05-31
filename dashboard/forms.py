from django import forms
from audio_upload.models import AudioFile

class AudioFileUploadForm(forms.ModelForm):
    class Meta:
        model = AudioFile
        fields = ['file']
        help_texts = {
            'file': 'Por favor, sube un archivo de audio en formato .mp3 o .wav. El tamaño máximo permitido es 10MB.',
        }
        widgets = {
            'file': forms.FileInput(attrs={
                'aria-describedby': 'fileHelp'
            })
        }

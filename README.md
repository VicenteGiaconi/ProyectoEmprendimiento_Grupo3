# ProyectoEmprendimiento — Audio Transcription API

API REST en Django para subir archivos de audio y obtener transcripción, diarización y análisis de sentimiento en español usando Deepgram y `sentiment-analysis-spanish`.

## Requisitos

- Python 3.12+
- ffmpeg (opcional, para generar audios de prueba)
- Cuenta en [Deepgram](https://deepgram.com) (tier gratuito disponible)

## Instalación

```bash
# 1. Clonar el repositorio
git clone https://github.com/VicenteGiaconi/ProyectoEmprendimiento_Grupo3.git
cd ProyectoEmprendimiento_Grupo3

# 2. Crear y activar entorno virtual
python3 -m venv venv
source venv/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar variables de entorno
cp .env.example .env
```

Editar `.env` y completar los valores:

```env
SECRET_KEY=django-insecure-changeme   # Cambiar en producción
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DEEPGRAM_API_KEY=tu_api_key_aqui      # Obtener en console.deepgram.com
```

## Correr la app

```bash
# Aplicar migraciones (primera vez)
python manage.py migrate

# Iniciar servidor
python manage.py runserver
```

El servidor queda disponible en `http://127.0.0.1:8000`.

## Endpoints

| Método | URL | Descripción |
|--------|-----|-------------|
| `POST` | `/api/audio/upload/` | Subir y procesar un archivo de audio |
| `GET` | `/api/audio/list/` | Listar todos los audios procesados |

### Parámetros del endpoint de upload

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `file` | File | Sí | Archivo de audio (.mp3, .wav, .ogg, .mp4, .m4a, .webm) |
| `language` | String | No | Código de idioma (ej. `es`, `en`). Si se omite, se detecta automáticamente. |

### Respuesta de ejemplo

```json
{
  "id": 1,
  "original_name": "llamada.wav",
  "content_type": "audio/wav",
  "size_bytes": 7802376,
  "uploaded_at": "2026-05-27T05:00:00Z",
  "file": "/media/audio/llamada.wav",
  "transcription": "No se encuentra, señorita, yo soy su mamá...",
  "transcription_status": "completed",
  "detected_language": "es",
  "diarization": [
    {
      "word": "No",
      "start": 0.08,
      "end": 0.24,
      "confidence": 0.99,
      "speaker": 0
    }
  ],
  "sentiment": {
    "average": {
      "sentiment": "neutral",
      "sentiment_score": 0.25
    },
    "segments": [
      {
        "text": "No se encuentra, señorita, yo soy su mamá.",
        "start": 0.0,
        "end": 4.2,
        "speaker": 0,
        "sentiment": "negative",
        "sentiment_score": 0.14
      }
    ]
  }
}
```

**Valores posibles de `sentiment`:** `positive`, `neutral`, `negative`

**`transcription_status`:** `completed` si Deepgram procesó el audio con éxito, `failed` si hubo un error.

## Testear la app

### Con un archivo propio

```bash
curl -X POST http://127.0.0.1:8000/api/audio/upload/ \
  -F "file=@/ruta/a/tu/audio.mp3" \
  | python3 -m json.tool
```

### Con un audio de prueba generado con ffmpeg

```bash
# Generar un tono de 3 segundos como MP3
ffmpeg -f lavfi -i "sine=frequency=440:duration=3" /tmp/test.mp3 -y

curl -X POST http://127.0.0.1:8000/api/audio/upload/ \
  -F "file=@/tmp/test.mp3" \
  | python3 -m json.tool
```

### Forzar idioma

```bash
curl -X POST http://127.0.0.1:8000/api/audio/upload/ \
  -F "file=@audio.wav" \
  -F "language=es" \
  | python3 -m json.tool
```

### Ver solo transcripción y sentimiento

```bash
curl -s -X POST http://127.0.0.1:8000/api/audio/upload/ \
  -F "file=@audio.wav" \
  | python3 -c "
import json, sys
data = json.load(sys.stdin)
print('TRANSCRIPCIÓN:', data['transcription'][:300])
print('IDIOMA:', data['detected_language'])
print('SENTIMIENTO:', json.dumps(data['sentiment']['average'], indent=2))
"
```

### Listar audios procesados

```bash
curl http://127.0.0.1:8000/api/audio/list/ | python3 -m json.tool
```

## Formatos de audio soportados

| Formato | MIME type |
|---------|-----------|
| MP3 | `audio/mpeg` |
| WAV | `audio/wav` |
| OGG | `audio/ogg` |
| MP4 / M4A | `audio/mp4` |
| WebM | `audio/webm` |

Tamaño máximo: **50 MB** (configurable con `MAX_AUDIO_SIZE_MB` en `settings.py`).

## Notas sobre el análisis de sentimiento

El sentimiento se analiza localmente con `sentiment-analysis-spanish`, un clasificador Naive Bayes entrenado en texto en español. Detecta bien los extremos (muy positivo / muy negativo) pero puede clasificar frases moderadamente positivas como neutrales.

Los umbrales utilizados son:
- `score >= 0.5` → `positive`
- `0.15 < score < 0.5` → `neutral`
- `score <= 0.15` → `negative`

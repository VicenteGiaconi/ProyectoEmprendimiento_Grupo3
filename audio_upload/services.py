import logging

from deepgram import DeepgramClient
from django.conf import settings

logger = logging.getLogger(__name__)


def transcribe_audio(file_path: str, language: str = None) -> dict:
    client = DeepgramClient(api_key=settings.DEEPGRAM_API_KEY)

    with open(file_path, 'rb') as f:
        audio_bytes = f.read()

    kwargs = dict(
        request=audio_bytes,
        model='nova-2',
        smart_format=True,
        diarize=True,
        sentiment=True,
        utterances=True,
    )

    if language:
        kwargs['language'] = language
    else:
        kwargs['detect_language'] = True

    response = client.listen.v1.media.transcribe_file(**kwargs)

    results = response.results
    alternative = results.channels[0].alternatives[0]

    transcript = alternative.transcript or ''

    detected_language = getattr(results.metadata if hasattr(results, 'metadata') else response.metadata, 'detected_language', None)
    logger.debug('detected_language: %s | transcript preview: %.80s', detected_language, transcript)
    logger.debug('results.sentiments: %s', results.sentiments)

    diarization = [
        {
            'word': w.word,
            'start': w.start,
            'end': w.end,
            'confidence': w.confidence,
            'speaker': getattr(w, 'speaker', None),
        }
        for w in (alternative.words or [])
    ]

    sentiment = _extract_sentiment(results)

    return {
        'transcript': transcript,
        'detected_language': detected_language,
        'diarization': diarization,
        'sentiment': sentiment,
    }


def _extract_sentiment(results) -> dict:
    if results.sentiments and results.sentiments.average:
        return {
            'average': {
                'sentiment': results.sentiments.average.sentiment,
                'sentiment_score': results.sentiments.average.sentiment_score,
            },
            'segments': [
                {
                    'text': s.text,
                    'start_word': s.start_word,
                    'end_word': s.end_word,
                    'sentiment': s.sentiment,
                    'sentiment_score': s.sentiment_score,
                }
                for s in (results.sentiments.segments or [])
            ],
        }

    utterances = results.utterances or []
    utterance_sentiments = [
        {
            'text': u.transcript,
            'start': u.start,
            'end': u.end,
            'speaker': u.speaker,
            'sentiment': getattr(u, 'sentiment', None),
            'sentiment_score': getattr(u, 'sentiment_score', None),
        }
        for u in utterances
        if getattr(u, 'sentiment', None) is not None
    ]

    if utterance_sentiments:
        return {'segments': utterance_sentiments}

    return {}

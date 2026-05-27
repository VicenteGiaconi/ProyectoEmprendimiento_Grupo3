from django.urls import path
from .views import AudioUploadView, AudioListView

urlpatterns = [
    path('upload/', AudioUploadView.as_view(), name='audio-upload'),
    path('list/', AudioListView.as_view(), name='audio-list'),
]

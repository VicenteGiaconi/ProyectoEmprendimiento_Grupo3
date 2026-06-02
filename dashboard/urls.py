from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('upload/', views.upload_audio, name='upload_audio'),
    path('detail/<int:audio_file_id>/', views.detail, name='detail'),
]

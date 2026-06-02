from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/audio/', include('audio_upload.urls')),
    path('', include('dashboard.urls')),  # Añadida la ruta al dashboard
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

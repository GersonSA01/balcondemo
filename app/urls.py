from django.urls import path
from .views import balcon_view, chat_api, taxonomia_api, estudiante_api, serve_pdf, create_ticket

urlpatterns = [
    path('', balcon_view, name='balcon'),
    path('api/chat/', chat_api, name='chat_api'),
    path('api/taxonomia/', taxonomia_api, name='taxonomia_api'),
    path('api/estudiante/', estudiante_api, name='estudiante_api'),
    path('api/pdf/<path:pdf_path>', serve_pdf, name='serve_pdf'),  # <path:> permite subdirectorios
    path('api/handoff/create_ticket/', create_ticket, name='create_ticket'),
]


# boletos/urls.py
from django.urls import path
from .views import FileUploadView, trigger_boleto_processing

urlpatterns = [
    path("upload_file/", FileUploadView.as_view(), name="upload-file"),
    path("manual_trigger/", trigger_boleto_processing, name="manual-trigger"),
]

import json
from unittest import mock

import django
import pytest
import datetime
from unittest.mock import patch, Mock
from django.http import JsonResponse
from django.test import RequestFactory
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files import File
from .models import Boleto
from .views import (
    BoletoGenerator,
    BoletoShipper,
    trigger_boleto_processing,
    FileUploadView,
)


@pytest.mark.django_db
@mock.patch("kanastra.models.Boleto.save")
@mock.patch("django.core.files.uploadedfile.SimpleUploadedFile")
@mock.patch("kanastra.views.BoletoShipper.enviar_boleto")
def test_generate_boleto_pdf(
    mock_save_file, mock_simple_upload_file, mock_enviar_boleto
):
    boleto = Boleto.objects.create(
        debt_id="12345",
        name="Teste",
        email="test@example.com",
        government_id="321",
        debt_amount="5000",
        debt_due_date=datetime.datetime.now(),
    )

    mock_simple_upload_file.return_value = mock.MagicMock(spec=SimpleUploadedFile)

    BoletoGenerator.generate_boleto_pdf(boleto)

    assert boleto.file is not None
    assert mock_save_file.called
    assert mock_enviar_boleto.called


@pytest.mark.django_db
def test_enviar_boleto():
    file_mock = mock.MagicMock(spec=File, name="FileMock")
    file_mock.name = "filename.pdf"

    boleto = Boleto.objects.create(
        debt_id="12345",
        name="Teste",
        email="test@example.com",
        government_id="321",
        debt_amount="5000",
        debt_due_date=datetime.datetime.now(),
        file=file_mock,
    )

    BoletoShipper.enviar_boleto(boleto)
    assert boleto.sent_on is not None


@pytest.mark.django_db
def test_trigger_boleto_processing():
    factory = RequestFactory()
    request = factory.post("manual_trigger")

    file_mock = mock.MagicMock(spec=File, name="FileMock")
    file_mock.name = "filename.pdf"

    Boleto.objects.create(
        debt_id="1",
        name="Teste 1",
        email="test1@example.com",
        government_id="111",
        debt_amount="5000",
        debt_due_date=datetime.datetime.now(),
        file=file_mock,
    )

    Boleto.objects.create(
        debt_id="2",
        name="Teste 2",
        email="test2@example.com",
        government_id="222",
        debt_amount="6000",
        debt_due_date=datetime.datetime.now(),
    )

    # Mock para BoletoGenerator
    with patch(
        "kanastra.views.BoletoGenerator.generate_boleto_pdf"
    ) as mock_generate_boleto_pdf:
        response = trigger_boleto_processing(request)

        assert response.status_code == 200
        assert "Gerando PDFs" in response.content.decode()
        assert mock_generate_boleto_pdf.call_count == 1


def test_file_upload_view_large_file():
    factory = RequestFactory()

    # Simulando o upload de um arquivo grande
    large_file = SimpleUploadedFile(
        "large_test.csv", b"A" * (500 * 1024 * 1024 + 1)
    )  # 500 MB + 1 byte

    request = factory.post("upload_file", {"file": large_file}, format="multipart")

    view = FileUploadView.as_view()
    response = view(request)

    assert response.status_code == 400
    assert {"error": "O arquivo enviado é muito grande"} == json.loads(response.content)

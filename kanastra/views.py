import csv
import datetime
import io
import logging
import os
import shutil
import tempfile
import time
import subprocess

from multiprocessing import Pool, cpu_count
from functools import partial
from django import db
from django.db import transaction
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import HttpResponseNotAllowed, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from .models import Boleto


logger = logging.getLogger(__name__)
# Create your views here.


class BoletoGenerator:
    @staticmethod
    def generate_boleto_pdf(boleto: Boleto) -> None:
        """
        Gera um arquivo PDF para o boleto.
        """
        if boleto.file:
            logger.info(f"Arquivo PDF para boleto {boleto.debt_id} já existente.")
            return

        logger.info(f"Iniciando criação de arquivo PDF para boleto {boleto.debt_id}")

        # lógica em mock para criação de PDF
        temp_file = SimpleUploadedFile(
            f"file_mock_{boleto.debt_id}.pdf", b"mock content"
        )
        boleto.file = temp_file
        boleto.save()

        logger.info(f"Arquivo PDF gerado para boleto {boleto.debt_id}")
        BoletoShipper().enviar_boleto(boleto)


class BoletoShipper:
    @staticmethod
    def enviar_boleto(boleto: Boleto) -> None:
        """
        Envia o arquivo PDF do boleto para o cliente.
        """
        if not boleto.file:
            raise Exception(
                f"Falha ao enviar boleto, arquivo PDF não encontrado para {boleto.debt_id}"
            )

        if boleto.sent_on:
            raise Exception(
                f"Falha ao enviar boleto, o boleto {boleto.debt_id} já foi enviado em {boleto.sent_on}"
            )

        logger.info(f"Iniciando envio de arquivo PDF para boleto {boleto.debt_id}")

        # lógica em mock para envio de PDF
        boleto.sent_on = datetime.datetime.now()
        boleto.save()

        logger.info(
            f"Arquivo PDF {boleto.debt_id} enviado com sucesso para {boleto.email}"
        )

        return


# Função mock para teste de processamento dos boletos, visto que essa funcionalidade deveria ser executada
# por uma rotina agendada de processamento para criação dos arquivos PDFs e envio de emails
@csrf_exempt
def trigger_boleto_processing(request):
    """
    Método de testes apenas para triggar a funcionalidade de processamento de
    boletos que em teoria seria triggada por uma rotina de agendamento
    """
    if request.method == "POST":
        pending_boletos = Boleto.objects.filter(file="")
        for boleto in pending_boletos:
            BoletoGenerator().generate_boleto_pdf(boleto=boleto)

        return JsonResponse(
            {"status": f"Gerando PDFs para {pending_boletos.count()} boletos"},
            status=200,
        )

    return JsonResponse({"error": "Método HTTP não permitido"}, status=405)


@method_decorator(csrf_exempt, name="dispatch")
class FileUploadView(View):
    def _process_csv_part(
        self,
        file_path: str,
        existing_boletos: set,
        has_header: bool,
    ) -> int:
        # Fechando todas as conexões do banco para evitar que a mesma conexão seja
        # utilizada por múltiplos processos
        db.connections.close_all()

        # Listas para armazenar objetos a serem criados em lote
        boletos_to_create = []

        header = [
            "name",
            "governmentId",
            "email",
            "debtAmount",
            "debtDueDate",
            "debtId",
        ]

        # Abrir o arquivo CSV e processar linha por linha
        with open(file_path, "r") as file:
            reader = (
                csv.DictReader(file)
                if has_header
                else csv.DictReader(file, fieldnames=header)
            )

            # Processar cada linha do arquivo split
            for row in reader:
                debt_id = row["debtId"]
                # Verificar se o boleto já existe
                if debt_id not in existing_boletos:
                    boleto_to_be_created = Boleto(
                        debt_id=debt_id,
                        name=row["name"],
                        email=row["email"],
                        government_id=row["governmentId"],
                        debt_amount=row["debtAmount"],
                        debt_due_date=row["debtDueDate"],
                    )
                    boletos_to_create.append(boleto_to_be_created)

        # Salvar boletos em lote
        if boletos_to_create:
            with transaction.atomic():
                Boleto.objects.bulk_create(boletos_to_create, ignore_conflicts=True)

        return len(boletos_to_create)  # Retorna o número de objetos criados

    def post(self, request):
        try:
            start_time = time.time()  # Marca o tempo de início
            if "file" not in request.FILES:
                return JsonResponse({"error": "Arquivo não encontrado"}, status=400)

            file = request.FILES["file"]

            max_file_size = 500 * 1024 * 1024  # 500 MB de limite de tamanho do arquivo
            if file.size > max_file_size:
                return JsonResponse(
                    {"error": "O arquivo enviado é muito grande"}, status=400
                )

            """ 
            Visando aumentar a performance para o endpoint de upload de arquivos, a leitura do arquivo e criação 
            de entidades no banco de dados poderiam ser feitas de maneira async. Nesse tipo de abordagem o
            endpoint serviria apenas para fazer o upload do arquivo para o servidor, e uma vez que o arquivo estivesse 
            no servidor, um serviço CRON efetuaria a leitura desse arquivo e criação das entidades no banco sem que 
            haja a necessidade do usuário esperar por esse processo ao fazer a requisição HTTP.
            """

            TMP_FILE_DIR = (
                "/app/tmp/split_files"  # Diretório onde os arquivos CSV serão salvos
            )

            if not os.path.exists(TMP_FILE_DIR):  # Garantir que o diretório exista
                os.makedirs(TMP_FILE_DIR)  # Cria o diretório se ele não existir

            FILE_PATH = os.path.join(TMP_FILE_DIR, "uploaded_file.csv")
            NUM_CORES = cpu_count()

            # Salvar o arquivo no disco para poder processar em partes
            with open(FILE_PATH, "wb") as f:
                for chunk in file.chunks():
                    f.write(chunk)

            # Dividir o arquivo em partes menores para processamento paralelo
            subprocess.run(
                [
                    "split",
                    "--lines=100000",
                    "--numeric-suffixes=1",
                    "--additional-suffix=.csv",
                    FILE_PATH,
                    "split_csv_part_",
                ],
                cwd=TMP_FILE_DIR,
                check=True,
                text=True,
                capture_output=True,
            )

            # Obter todos os arquivos "split"
            split_files = [
                f for f in os.listdir(TMP_FILE_DIR) if f.startswith("split_csv_part")
            ]

            with transaction.atomic():
                existing_boletos = set(
                    Boleto.objects.all().values_list("debt_id", flat=True)
                )

            # Criar informações adicionais (caminho do arquivo e se contém cabeçalho)
            file_infos = [
                (
                    os.path.join(TMP_FILE_DIR, f),
                    existing_boletos,
                    i == 0,
                )
                for i, f in enumerate(split_files)
            ]

            with Pool(processes=NUM_CORES) as pool:
                process_func = partial(
                    self._process_csv_part,
                )
                results = pool.starmap(process_func, file_infos)

            # Contar o total de objetos criados
            total_boletos = sum(r for r in results)

            end_time = time.time()
            logger.info(
                f"A função de upload demorou {end_time - start_time:.4f} segundos para executar"
            )
            # Limpar o diretório temporário após o processamento
            if os.path.exists(TMP_FILE_DIR):
                shutil.rmtree(TMP_FILE_DIR)  # Remove o diretório e seu conteúdo
                os.makedirs(TMP_FILE_DIR)  # Recria o diretório vazio

            return JsonResponse(
                {
                    "status": "Arquivo processado com sucesso",
                    "boletos_created": total_boletos,
                }
            )
        except Exception as ex:
            # Limpar o diretório temporário após o processamento
            if os.path.exists(TMP_FILE_DIR):
                shutil.rmtree(TMP_FILE_DIR)  # Remove o diretório e seu conteúdo
                os.makedirs(TMP_FILE_DIR)  # Recria o diretório vazio

            logger.warning(ex)
            return JsonResponse(
                {
                    "status": "Erro no processamento do arquivo",
                },
                status=400,
            )

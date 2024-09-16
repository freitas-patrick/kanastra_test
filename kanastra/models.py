import logging

from django.db import models

logger = logging.getLogger(__name__)


"""
Em um cenário real provavelmente seria usado um banco NoSQL para performance e talvez essa entidade seria dividida em duas
Uma para cliente e outra para boleto
"""


class Boleto(models.Model):
    debt_id = models.CharField(max_length=255, unique=True, db_index=True)
    name = models.CharField(max_length=255, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    government_id = models.CharField(max_length=30, null=True, blank=True)
    debt_amount = models.DecimalField(max_digits=10, decimal_places=2)
    debt_due_date = models.DateField()
    file = models.FileField(upload_to="boletos/", null=True, blank=True)
    sent_on = models.DateTimeField(
        null=True, blank=True
    )  # Data e hora de envio do email

    def __str__(self):
        return f"{self.debt_id}"

import logging

from celery import shared_task

logger = logging.getLogger(__name__)

@shared_task
def generate_certificate_task(enrollment_id):
    logger.info(f"Generating certificate for enrollment {enrollment_id}")
    return True

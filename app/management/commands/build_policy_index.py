from django.core.management.base import BaseCommand
from app.services.policy_index import build_index

class Command(BaseCommand):
    help = "Construye el índice TF-IDF del reglamento (PDF → artículos)"

    def handle(self, *args, **kwargs):
        try:
            n_art, vocab = build_index()
            self.stdout.write(
                self.style.SUCCESS(f"✅ OK: {n_art} artículos indexados, vocab {vocab} términos")
            )
        except FileNotFoundError as e:
            self.stdout.write(
                self.style.ERROR(f"❌ Error: {e}")
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"❌ Error al construir índice: {e}")
            )



















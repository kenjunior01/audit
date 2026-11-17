"""Seed de credenciais de IA NVIDIA NIM: env → BD encriptada (Fernet).

Uso:
  python manage.py seed_nim_credentials            # copia env para a BD
  python manage.py seed_nim_credentials --clear    # limpa a BD (fallback env)

Env lidas: AUDIT_NVIDIA_API_KEY (ou NVIDIA_API_KEY) → slot text;
AUDIT_NIM_VISION_API_KEY → vision; AUDIT_NIM_IMAGE_API_KEY → image.
"""
from django.core.management.base import BaseCommand

from dashboard import ai_credentials


class Command(BaseCommand):
    help = "Copia credenciais NVIDIA NIM das env para a BD (encriptadas)."

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true",
                            help="Limpa as credenciais da BD (fallback env).")

    def handle(self, *args, **options):
        if options.get("clear"):
            for slot in ai_credentials.VALID_SLOTS:
                ai_credentials.save_slot(slot, api_key="")
            self.stdout.write(self.style.WARNING(
                "Credenciais IA limpas da BD — a resolver por env."))
            return

        copied, skipped = [], []
        for slot in ai_credentials.VALID_SLOTS:
            d = ai_credentials.SLOT_DEFAULTS[slot]
            key = ""
            for env_name in d["key_envs"]:
                key = ai_credentials.os_env(env_name) or ""
                if key.strip():
                    key = key.strip()
                    break
            if not key:
                skipped.append(slot)
                continue
            model = (ai_credentials.os_env(d["model_env"]) or "").strip()
            base = (ai_credentials.os_env(d["base_env"]) or "").strip()
            ai_credentials.save_slot(slot, api_key=key,
                                     model=model or None,
                                     base_url=base or None)
            copied.append(slot)
        if copied:
            self.stdout.write(self.style.SUCCESS(
                "Credenciais copiadas para a BD (encriptadas): "
                + ", ".join(copied)))
        if skipped:
            self.stdout.write(self.style.NOTICE(
                "Sem env para: " + ", ".join(skipped)))
        for slot, info in ai_credentials.public_status().items():
            self.stdout.write(
                f"  {slot}: source={info['source'] or '—'} "
                f"masked={info['masked'] or '—'} model={info['model']}")

"""
Migration 0038 — Excel Studio:
  • Novo modelo ExcelImportJob (trilha de auditoria das importações)
  • Índices de performance em Transaction, Alert e AuditCase
Gerada manualmente para não exigir execução local do Django.
"""
from django.db import migrations, models
from django.db.models import Index


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0037_riskagent_external_action_template'),
    ]

    operations = [
        migrations.CreateModel(
            name='ExcelImportJob',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('file_name', models.CharField(max_length=256)),
                ('uploaded_by', models.CharField(blank=True, max_length=128, null=True)),
                ('sheet', models.CharField(blank=True, max_length=128, null=True)),
                ('rows_imported', models.IntegerField(default=0)),
                ('rows_skipped', models.IntegerField(default=0)),
                ('mapping', models.JSONField(blank=True, default=dict)),
                ('errors', models.JSONField(blank=True, default=list)),
                ('status', models.CharField(choices=[('Completed', 'Concluída'), ('Partial', 'Parcial'), ('Failed', 'Falhada')], default='Completed', max_length=32)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='transaction',
            index=Index(fields=['timestamp'], name='dashboard_tx_ts_idx'),
        ),
        migrations.AddIndex(
            model_name='transaction',
            index=Index(fields=['status'], name='dashboard_tx_status_idx'),
        ),
        migrations.AddIndex(
            model_name='transaction',
            index=Index(fields=['vendor'], name='dashboard_tx_vendor_idx'),
        ),
        migrations.AddIndex(
            model_name='alert',
            index=Index(fields=['timestamp'], name='dashboard_alert_ts_idx'),
        ),
        migrations.AddIndex(
            model_name='alert',
            index=Index(fields=['severity'], name='dashboard_alert_sev_idx'),
        ),
        migrations.AddIndex(
            model_name='alert',
            index=Index(fields=['status'], name='dashboard_alert_status_idx'),
        ),
        migrations.AddIndex(
            model_name='auditcase',
            index=Index(fields=['status'], name='dashboard_case_status_idx'),
        ),
        migrations.AddIndex(
            model_name='auditcase',
            index=Index(fields=['created_at'], name='dashboard_case_created_idx'),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0033_auditrule_domain'),
    ]

    operations = [
        migrations.AddField(
            model_name='contextprofile',
            name='regulatory_frameworks',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='contextprofile',
            name='audit_domains',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='contextprofile',
            name='risk_appetite',
            field=models.CharField(default='Balanced', max_length=32),
        ),
    ]


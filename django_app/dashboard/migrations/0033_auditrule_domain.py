from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0032_auditrule_auditcase_action_due_date_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='auditrule',
            name='domain',
            field=models.CharField(default='General', max_length=64),
        ),
    ]


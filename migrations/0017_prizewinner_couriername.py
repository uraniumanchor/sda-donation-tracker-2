# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0016_auto_20151121_1416'),
    ]

    operations = [
        migrations.AddField(
            model_name='prizewinner',
            name='couriername',
            field=models.CharField(help_text=b'e.g. FedEx, DHL, ...', max_length=64, verbose_name=b'Courier Service Name', blank=True),
        ),
    ]

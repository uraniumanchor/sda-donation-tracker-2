# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0013_add_prizewinner_notes'),
    ]

    operations = [
        migrations.AddField(
            model_name='prize',
            name='requiresshipping',
            field=models.BooleanField(default=True, verbose_name=b'Requires Postal Shipping'),
        ),
    ]

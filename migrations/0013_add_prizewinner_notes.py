# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0012_donor_user'),
    ]

    operations = [
        migrations.AddField(
            model_name='prizewinner',
            name='shippingnotes',
            field=models.TextField(max_length=2048, verbose_name=b'Shipping Notes', blank=True),
        ),
        migrations.AddField(
            model_name='prizewinner',
            name='winnernotes',
            field=models.TextField(max_length=1024, verbose_name=b'Winner Notes', blank=True),
        ),
    ]

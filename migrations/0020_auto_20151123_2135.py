# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0019_prize_reviewnotes'),
    ]

    operations = [
        migrations.AddField(
            model_name='prizewinner',
            name='acceptdeadline',
            field=models.DateTimeField(default=None, help_text=b'The deadline for this winner to accept their prize (leave blank for no deadline)', null=True, verbose_name=b'Winner Accept Deadline', blank=True),
        ),
        migrations.AlterField(
            model_name='prize',
            name='reviewnotes',
            field=models.TextField(help_text=b'Notes for the contributor (for example, why a particular prize was denied)', max_length=1024, verbose_name=b'Review Notes', blank=True),
        ),
    ]

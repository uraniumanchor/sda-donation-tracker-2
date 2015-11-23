from django.core.management.base import BaseCommand, CommandError

import settings

import tracker.viewutil as viewutil
import tracker.prizemail as prizemail

class Command(BaseCommand):
    help = 'Sends emails for all prizes that have been shipped'

    def add_arguments(self, parser):
        parser.add_argument('-e', '--event', help='specify which event', required=True)
        parser.add_argument('-t', '--template', help='specify an email template', required=True)

    def handle(self, *args, **options):
        event = viewutil.get_event(options['event'])
        prizeWinners = prizemail.prizes_with_shipping_email_pending(event)
        emailTemplate = options['template'] or event.prizeshippedemailtemplate
        
        if emailTemplate == None:
            print("No default prize shipped email template specified on event {0}, cannot send e-mails.".format(event.short))
        else:
            prizemail.automail_shipping_email_notifications(event, prizeWinners, emailTemplate)

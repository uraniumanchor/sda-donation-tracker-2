from django.core.urlresolvers import reverse
import django.contrib.auth as djauth
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils.safestring import mark_safe
from django.contrib.auth import get_user_model

import post_office.mail
import post_office.models

import settings

import tracker.viewutil as viewutil

# Future proofing against replacing auth model
AuthUser = get_user_model()

class EmailLoginAuthBackend:
    """Custom authentication backend which supports 
    e-mail as identity. Note that if more than one user has
    the same e-mail, they will all not be able to use that 
    email and must use the user id instead"""

    supports_inactive_user = False

    def authenticate(self, username=None, password=None, email=None):
        AUTH_METHODS = [
            {'email': username},
            {'email': email},
        ]

        try:
            userFilter = AuthUser.objects.none()
            for method in AUTH_METHODS:
                userFilter = AuthUser.objects.filter(**method)
                if userFilter.count() == 1:
                    user = userFilter[0]
                    if user.check_password(password):
                        return user
        except Exception as e:
            pass
        return None

    def get_user(self, user_id):
        try:
            return AuthUser.objects.get(pk=user_id)
        except AuthUser.DoesNotExist:
            return None

def get_password_reset_email_template_name():
    return getattr(settings, 'PASSWORD_RESET_EMAIL_TEMPLATE_NAME', 'password_reset_template')

#TODO: there should probably be something in the admin to manage the default email templates
#TODO: get better control over when the auth links expire, and explicitly state the expiration time
def get_password_reset_email_template():
    return post_office.models.EmailTemplate.objects.get_or_create(
        name=get_password_reset_email_template_name(), 
        defaults={
            'subject': 'Password Reset',
            'content': """Hello {{ user }},
    You (or something pretending to be you) has requested a password reset for your account on {{ domain }}. Please follow this <a href="{{ reset_url }}">link</a> to reset your password.

    This login link will expire after you reset your password.

    - The Staff
""",
        })[0]

# This will ensure the template always exists on server boot-up
_ensurePasswordResetEmailTemplateExists = get_password_reset_email_template()

def get_register_email_template_name():
    return getattr(settings, 'REGISTER_EMAIL_TEMPLATE_NAME', 'register_email_template')

def get_register_email_template():
    return post_office.models.EmailTemplate.objects.get_or_create(
        name=get_register_email_template_name(), 
        defaults={
            'subject': 'Account Registration',
            'content': """Hello {{ user }},
    You (or something pretending to be you) has requested an account on {{ domain }}. Please follow this <a href="{{ reset_url }}">link</a> to complete registering your account.

    This login link will only work once to register your account.

    - The Staff
""",
        })[0]

_ensureRegisterEmailTemplateExists = get_register_email_template()

def make_auth_token_url_suffix(user, token_generator=default_token_generator):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = token_generator.make_token(user)
    return 'uidb64={0}&token={1}'.format(uid,token)
        
def make_auth_token_url(domain, user, viewURI, token_generator=default_token_generator):
    return domain + viewURI + '?' + make_auth_token_url_suffix(user, token_generator)
        
def send_password_reset_mail(domain, user, template=get_password_reset_email_template(), sender=None, token_generator=default_token_generator):
    return send_auth_token_mail(domain, user, reverse('password_reset_confirm'), template, sender, token_generator)

def send_registration_mail(domain, user, template=get_register_email_template(), sender=None, token_generator=default_token_generator):
    return send_auth_token_mail(domain, user, reverse('confirm_registration'), template, sender, token_generator)
  
def send_auth_token_mail(domain, user, viewURI, template, sender=None, token_generator=default_token_generator):
    if not sender:
        sender = viewutil.get_default_email_from_user()
    reset_url = make_auth_token_url(domain, user, viewURI, token_generator)
    formatContext = {
        'user': user,
        'domain': domain,
        'reset_url': mark_safe( reset_url ),
    }
    return post_office.mail.send(recipients=[user.email], sender=sender, template=template, context=formatContext)

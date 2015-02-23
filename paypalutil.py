from paypal.standard.ipn.forms import PayPalIPNForm
from paypal.standard.ipn.models import PayPalIPN
from tracker.models import *
from datetime import *
import tracker.viewutil as viewutil
import random

from decimal import *
import pytz

def initialize_ipn_object(request):
  flag = None
  ipn_obj = None
  form = PayPalIPNForm(request.POST)
  if form.is_valid():
    try:
      ipn_obj = form.save(commit=False)
    except Exception, e:
      flag = "Exception while processing. (%s)" % e
  else:
    flag = "Invalid form. (%s)" % form.errors
  if ipn_obj is None:
    ipn_obj = PayPalIPN()
  ipn_obj.initialize(request)
  if flag is not None:
    ipn_obj.set_flag(flag)
  return ipn_obj

def initialize_paypal_donation(donation, ipnObj):
  defaults = {
    'email'           : ipnObj.payer_email.lower(),
    'firstname'       : ipnObj.first_name,
    'lastname'        : ipnObj.last_name,
    'addressstreet'  : ipnObj.address_street,
    'addresscity'    : ipnObj.address_city,
    'addresscountry' : ipnObj.address_country,
    'addressstate'   : ipnObj.address_state,
    'addresszip'     : ipnObj.address_zip,
    'visibility'      : 'ANON',
  }
  donor,created = Donor.objects.get_or_create(paypalemail=ipnObj.payer_email.lower(),defaults=defaults)

  if donation:
    if donation.requestedvisibility != 'CURR':
      donor.visibility = donation.requestedvisibility
    if donation.requestedalias and (not donor.alias or donation.requestedalias.lower() != donor.alias.lower()):
      foundAResult = False
      currentAlias = donation.requestedalias
      while not foundAResult:
        results = Donor.objects.filter(alias__iexact=currentAlias)
        if results.exists():
          currentAlias = donation.requestedalias + str(random.getrandbits(8))
        else:
          foundAResult = True
      donor.alias = currentAlias
    if donation.requestedemail and donation.requestedemail != donor.email and not Donor.objects.filter(email=donation.requestedemail).exists():
      donor.email = donation.requestedemail
  donor.save()

  if not donation:
    donation = Donation.objects.create()

  donation.domain='PAYPAL'
  donation.domainId=ipnObj.txn_id
  donation.donor=donor
  donation.amount=Decimal(ipnObj.mc_gross)
  donation.currency=ipnObj.mc_currency
  if not donation.timereceived:
    donation.timereceived = datetime.utcnow()
  donation.testdonation=ipnObj.test_ipn
  donation.fee=Decimal(ipnObj.mc_fee or 0)
  #donation.event = Event.objects.latest()

  # if the user attempted to tamper with the donation amount, remove all bids
  if donation.amount != ipnObj.mc_gross:
    donation.modcomment += u"\n*Tampered donation amount from " + str(donation.amount) + u" to " + str(ipnObj.mc_gross) + u", removed all bids*"
    donation.amount = ipnObj.mc_gross
    donation.bids.clear()
    viewutil.tracker_log('paypal', 'Tampered amount detected in donation {0} (${1} -> ${2})'.format(donation.id, donation.amount, ipnObj.mc_gross), event=donation.event) 

  paymentStatus = ipnObj.payment_status.lower()

  if not ipnObj.flag:
    if paymentStatus == 'pending':
      donation.transactionstate = 'PENDING'
    elif paymentStatus == 'completed' or paymentStatus == 'canceled_reversal' or paymentStatus == 'processed':
      donation.transactionstate = 'COMPLETED'
    elif paymentStatus == 'refunded' or paymentStatus == 'reversed' or paymentStatus == 'failed' or paymentStatus == 'voided':
      donation.transactionstate = 'CANCELLED'
    else:
      donation.transactionstate = 'FLAGGED'
      viewutil.tracker_log('paypal', 'Unknown payment status in donation {0} ({1})'.format(donation.id, paymentStatus), event=donation.event)
  else:
    donation.transactionstate = 'FLAGGED'
    viewutil.tracker_log('paypal', 'IPN object flagged for donation {0} ({1})'.format(donation.id, ipnObj.txn_id), event=donation.event)

  donation.save()
  # I think we only care if the _donation_ was freshly created
  return donation

def get_paypal_donation(paypalemail, amount, transactionid):
  donations = Donation.objects.filter(amount=amount, domain='PAYPAL', domainId=transactionid)
  if donations.exists():
    donation = donations[0]
    donors = Donor.objects.filter(paypalemail=paypalemail)
    if donors.exists() and donation.donor.id == donors[0].id:
      return donation
  return None

_reasonCodeDetails = {
'echeck': ("Payments sent as eCheck tend to take several days to a week to clear. Unfortuantely, there is nothing we can do to expidite this process. In the future, please consider using instant-payment type payments.", False),
'paymentreview': ("The payment is being reviewed by PayPal. Typically, this will occur with large transaction amounts and/or from accounts with low overall activity.", False),
'regulatory_review': ("This payment is being reviewed for compliance with government regulations.", False),
'intl': ("The payment was sent via a currency the target account is not set up to receive, and must be confirmed manually by the account holder.", True),
'multi-currency': ("The payment was sent in a currency the target account cannot convert from, and must be manually converted by the account holder.", True),
'unilateral': ("The receiver account e-mail has not yet been confirmed", True),
'upgrade': ("The receiver account is unable to process the payment, due to its account status", True),
}


def get_pending_reason_details(pending_reason):
  return _reasonCodeDetails.get(pending_reason, ('', True))

def log_ipn(ipnObj, donation=None, message=''):
  message = str(message) + '\ntxn id : ' + ipnObj.txn_id + '\nstatus : ' + ipnObj.payment_status + '\nemail  : ' + ipnObj.payer_email + '\namount : ' + str(ipnObj.mc_gross) + '\ndate   : ' + str(ipnObj.payment_date)
  status = ipnObj.payment_status.lower()
  if status == 'pending':
    message += 'pending : ' + ipnObj.pending_reason
  elif status in ['reversed', 'refunded', 'canceled_reversal', 'denied']:
    message += 'reason  : ' + ipnObj.reason_code
  viewutil.tracker_log('paypal', message, event=donation.event if donation else None)

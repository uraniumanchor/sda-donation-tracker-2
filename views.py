import django
import traceback

from django import shortcuts
from django.shortcuts import render,render_to_response, redirect

from django.db import connection
from django.db.models import Count,Sum,Min,Max,Avg,Q
from django.db.utils import ConnectionDoesNotExist,IntegrityError
from django.db import transaction

from django.forms import ValidationError

from django.core import serializers,paginator
from django.core.paginator import Paginator
from django.core.cache import cache
from django.core.exceptions import FieldError,ObjectDoesNotExist
from django.core.urlresolvers import reverse

from django.contrib.auth import authenticate,login as auth_login,logout as auth_logout, get_user_model
from django.contrib.auth.forms import AuthenticationForm
import django.contrib.auth.views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator

from django.http import HttpResponse,HttpResponseRedirect,Http404

from django import template
from django.template import RequestContext
from django.template.base import TemplateSyntaxError

from django.views.decorators.cache import never_cache,cache_page
from django.views.decorators.csrf import csrf_protect,csrf_exempt,get_token as get_csrf_token
from django.views.decorators.http import require_POST
from django.views.generic import View, TemplateView

import post_office.mail

from django.utils import translation
from django.utils.http import urlsafe_base64_decode 
from django.utils import timezone
import simplejson as json

from paypal.standard.forms import PayPalPaymentsForm
from paypal.standard.ipn.models import PayPalIPN
from paypal.standard.ipn.forms import PayPalIPNForm

from tracker.models import *
from tracker.forms import *
import tracker.filters as filters

import tracker.viewutil as viewutil
import tracker.paypalutil as paypalutil

import gdata.spreadsheet.service
import gdata.spreadsheet.text_db

from decimal import Decimal
from dateutil.relativedelta import relativedelta
import sys
import datetime
import settings
import logutil as log
import pytz
import random
import decimal
import re
import dateutil.parser
import itertools
import urllib2

def dv():
  return str(django.VERSION[0]) + '.' + str(django.VERSION[1]) + '.' + str(django.VERSION[2])

def pv():
  return str(sys.version_info[0]) + '.' + str(sys.version_info[1]) + '.' + str(sys.version_info[2])

def fixorder(queryset, orderdict, sort, order):
  queryset = queryset.order_by(*orderdict[sort])
  if order == -1:
    queryset = queryset.reverse()
  return queryset

@never_cache
def login(request):
  message = None
  if 'next' in request.GET:
    message = 'Login required to continue.'
  return auth_views.login(request, template_name='tracker/login.html', extra_context={'event': viewutil.get_event(None), 'csrftoken': get_csrf_token(request), 'message': message})

@never_cache
def logout(request):
  auth_logout(request)
  return django.shortcuts.redirect(request.META.get('HTTP_REFERER', settings.LOGOUT_REDIRECT_URL))

@never_cache
def password_reset(request):
  return auth_views.password_reset(request, 
    template_name='tracker/password_reset.html', 
    email_template_name='password_reset_template',
    password_reset_form=PostOfficePasswordResetForm,
    from_email=settings.EMAIL_FROM_USER, 
    extra_context={'event': viewutil.get_event(None), 'csrftoken': get_csrf_token(request)})

@never_cache
def password_reset_done(request):
  return tracker_response(request, 'tracker/password_reset_done.html')

@never_cache
def password_reset_confirm(request):
  uidb64 = request.GET['uidb64']
  token = request.GET['token']
  return auth_views.password_reset_confirm(request, 
    uidb64, 
    token, 
    template_name='tracker/password_reset_confirm.html', 
    extra_context={'event': viewutil.get_event(None), 'csrftoken': get_csrf_token(request)})

@never_cache
def password_reset_complete(request):
  return tracker_response(request, 'tracker/password_reset_complete.html', { 'login_url': reverse('login') })

@never_cache
@login_required
def password_change(request):
  return auth_views.password_change(request, template_name='tracker/password_change.html',extra_context={'csrftoken': get_csrf_token(request)})

@never_cache
@login_required
def password_change_done(request):
  return render(request, 'tracker/password_change_done.html') 

@never_cache
def confirm_registration(request):
  AuthUser = get_user_model()
  uidb64 = request.GET.get('uidb64', None)
  uid = urlsafe_base64_decode(uidb64) if uidb64 else None
  token = request.GET.get('token',None)
  user = None
  tokenGenerator = default_token_generator
  try:
    user = AuthUser.objects.get(pk=uid)
  except:
    user = None
  if request.method == 'POST':
    form = RegistrationConfirmationForm(user=user, token=token, token_generator=tokenGenerator, data=request.POST)
    if form.is_valid():
      form.save()
      return tracker_response(request, 'tracker/confirm_registration_done.html', {'user': form.user})
  else:
    form = RegistrationConfirmationForm(user=user, token=token, token_generator=tokenGenerator, initial={'userid': uid, 'authtoken': token, 'username': user.username if user else ''})
  return tracker_response(request, 'tracker/confirm_registration.html', {'formuser': user, 'tokenmatches': tokenGenerator.check_token(user, token) if token else False, 'form': form, 'csrftoken': get_csrf_token(request)})

def tracker_response(request=None, template='tracker/index.html', qdict={}, status=200):
  starttime = datetime.datetime.now()
  context = RequestContext(request)
  language = translation.get_language_from_request(request)
  translation.activate(language)
  request.LANGUAGE_CODE = translation.get_language()
  profile = None
  if request.user.is_authenticated():
    try:
      profile = request.user.get_profile()
    except UserProfile.DoesNotExist:
      profile = UserProfile()
      profile.user = request.user
      profile.save()
  if profile:
    template = profile.prepend + template
    prepend = profile.prepend
  else:
    prepend = ''
  authform = AuthenticationForm(request.POST)
  qdict.update({
    'djangoversion' : dv(),
    'pythonversion' : pv(),
    'user' : request.user,
    'profile' : profile,
    'prepend' : prepend,
    'next' : request.REQUEST.get('next', request.path),
    'starttime' : starttime,
    'events': Event.objects.all(),
    'authform' : authform })
  qdict.setdefault('event',viewutil.get_event(None))
  try:
    if request.user.username[:10]=='openiduser':
      qdict.setdefault('usernameform', UsernameForm())
      return render(request, 'tracker/username.html', dictionary=qdict)
    resp = render(request, template, dictionary=qdict, status=status)
    if 'queries' in request.GET and request.user.has_perm('tracker.view_queries'):
      return HttpResponse(json.dumps(connection.queries, ensure_ascii=False, indent=1),content_type='application/json;charset=utf-8')
    return resp
  except Exception,e:
    if request.user.is_staff and not settings.DEBUG:
      return HttpResponse(unicode(type(e)) + '\n\n' + unicode(e), mimetype='text/plain', status=500)
    raise

def eventlist(request):
  return tracker_response(request, 'tracker/eventlist.html', { 'events' : Event.objects.all() })

def index(request,event=None):
  event = viewutil.get_event(event)
  eventParams = {}
  if event.id:
    eventParams['event'] = event.id
  agg = filters.run_model_query('donation', eventParams, user=request.user, mode='user').aggregate(amount=Sum('amount'), count=Count('amount'), max=Max('amount'), avg=Avg('amount'))
  agg['target'] = event.targetamount
  count = {
    'runs' : filters.run_model_query('run', eventParams, user=request.user).count(),
    'prizes' : filters.run_model_query('prize', eventParams, user=request.user).count(),
    'bids' : filters.run_model_query('bid', eventParams, user=request.user).count(),
    'donors' : filters.run_model_query('donorcache', eventParams, user=request.user).values('donor').distinct().count(),
  }

  if 'json' in request.GET:
    return HttpResponse(json.dumps({'count':count,'agg':agg},ensure_ascii=False),content_type='application/json;charset=utf-8')
  elif 'jsonp' in request.GET:
    callback = request.GET['jsonp']
    return HttpResponse('%s(%s);' % (callback, json.dumps({'count':count,'agg':agg},ensure_ascii=False)), content_type='text/javascript;charset=utf-8')
  return tracker_response(request, 'tracker/index.html', { 'agg' : agg, 'count' : count, 'event': event })

@never_cache
def setusername(request):
  if not request.user.is_authenticated or request.user.username[:10]!='openiduser' or request.method != 'POST':
    return django.shortcuts.redirect(reverse('tracker.views.index'))
  usernameform = UsernameForm(request.POST)
  if usernameform.is_valid():
    request.user.username = request.POST['username']
    request.user.save()
    return shortcuts.redirect(request.POST['next'])
  return tracker_response(request, template='tracker/username.html', qdict={ 'usernameform' : usernameform })

modelmap = {
  'bid'           : Bid,
  'donationbid'   : DonationBid,
  'donation'      : Donation,
  'donor'         : Donor,
  'event'         : Event,
  'prize'         : Prize,
  'prizecategory' : PrizeCategory,
  'run'           : SpeedRun,
  'prizewinner'   : PrizeWinner,
}

permmap = {
  'run'          : 'speedrun'
  }
fkmap = { 'winner': 'donor', 'speedrun': 'run', 'startrun': 'run', 'endrun': 'run', 'category': 'prizecategory', 'parent': 'bid'}

related = {
  'bid'          : [ 'speedrun', 'event', 'parent' ],
  'allbids'          : [ 'speedrun', 'event', 'parent' ],
  'bidtarget'          : [ 'speedrun', 'event', 'parent' ],
  'donation'     : [ 'donor' ],
  'prize'        : [ 'category', 'startrun', 'endrun' ],
  'prizewinner'  : [ 'prize', 'winner' ],
}

defer = {
  'bid'    : [ 'speedrun__description', 'speedrun__endtime', 'speedrun__starttime', 'speedrun__runners', 'event__date'],
}

def donor_privacy_filter(model, fields):
  visibility = None
  primary = None
  prefix = ''
  if model == 'donor':
    visibility = fields['visibility']
    primary = True
  elif 'donor__visibility' in fields:
    visibility = fields['donor__visibility']
    primary = False
    prefix = 'donor__'
  elif 'winner__visibility' in fields:
    visibility = fields['winner__visibility']
    primary = False
    prefix = 'winner__'
  else:
    return
  for field in list(fields.keys()):
    if field.startswith(prefix + 'address') or field.startswith(prefix + 'runner') or field.startswith(prefix + 'prizecontributor') or 'email' in field:
      del fields[field]
  if visibility == 'FIRST' and fields[prefix + 'lastname']:
    fields[prefix + 'lastname'] = fields[prefix + 'lastname'][0] + "..."
  if (visibility == 'ALIAS' or visibility == 'ANON'):
    fields[prefix + 'lastname'] = None
    fields[prefix + 'firstname'] = None
    fields[prefix + 'public'] = fields[prefix + 'alias']
  if visibility == 'ANON':
    fields[prefix + 'alias'] = None
    fields[prefix + 'public'] = u'(Anonymous)'

def donation_privacy_filter(model, fields):
  primary = None
  if model == 'donation':
    primary = True
  elif 'donation__domainId' in fields:
    primary = False
  else:
    return
  prefix = ''
  if not primary:
    prefix = 'donation__'
  if fields[prefix + 'commentstate'] != 'APPROVED':
    fields[prefix + 'comment'] = None
  del fields[prefix + 'modcomment']
  del fields[prefix + 'fee']
  del fields[prefix + 'requestedalias']
  if prefix + 'requestedemail' in fields:
    del fields[prefix + 'requestedemail']
  del fields[prefix + 'requestedvisibility']
  del fields[prefix + 'testdonation']
  del fields[prefix + 'domainId']

def prize_privacy_filter(model, fields):
  if model != 'prize':
    return
  del fields['extrainfo']
  del fields['provideremail']

@never_cache
def search(request):
  authorizedUser = request.user.has_perm('tracker.can_search')
  #  return HttpResponse('Access denied',status=403,content_type='text/plain;charset=utf-8')
  try:
    searchParams = viewutil.request_params(request)
    searchtype = searchParams['type']
    qs = filters.run_model_query(searchtype, searchParams, user=request.user, mode='admin' if authorizedUser else 'user')
    if searchtype in related:
      qs = qs.select_related(*related[searchtype])
    if searchtype in defer:
      qs = qs.defer(*defer[searchtype])
    qs = qs.annotate(**viewutil.ModelAnnotations.get(searchtype,{}))
    if qs.count() > 1000:
      qs = qs[:1000]
    jsonData = json.loads(serializers.serialize('json', qs, ensure_ascii=False))
    objs = dict(map(lambda o: (o.id,o), qs))
    for o in jsonData:
      o['fields']['public'] = repr(objs[int(o['pk'])])
      for a in viewutil.ModelAnnotations.get(searchtype,{}):
        o['fields'][a] = unicode(getattr(objs[int(o['pk'])],a))
      for r in related.get(searchtype,[]):
        ro = objs[int(o['pk'])]
        for f in r.split('__'):
          if not ro: break
          ro = getattr(ro,f)
        if not ro: continue
        relatedData = json.loads(serializers.serialize('json', [ro], ensure_ascii=False))[0]
        for f in ro.__dict__:
          if f[0] == '_' or f.endswith('id') or f in defer.get(searchtype,[]): continue
          v = relatedData["fields"][f]
          o['fields'][r + '__' + f] = relatedData["fields"][f]
        o['fields'][r + '__public'] = repr(ro)
      if not authorizedUser:
        donor_privacy_filter(searchtype, o['fields'])
        donation_privacy_filter(searchtype, o['fields'])
        prize_privacy_filter(searchtype, o['fields'])
    resp = HttpResponse(json.dumps(jsonData,ensure_ascii=False),content_type='application/json;charset=utf-8')
    if 'queries' in request.GET and request.user.has_perm('tracker.view_queries'):
      return HttpResponse(json.dumps(connection.queries, ensure_ascii=False, indent=1),content_type='application/json;charset=utf-8')
    return resp
  except KeyError, e:
    return HttpResponse(json.dumps({'error': 'Key Error, malformed search parameters'}, ensure_ascii=False), status=400, content_type='application/json;charset=utf-8')
  except FieldError, e:
    return HttpResponse(json.dumps({'error': 'Field Error, malformed search parameters'}, ensure_ascii=False), status=400, content_type='application/json;charset=utf-8')
  except ValidationError, e:
    d = {'error': u'Validation Error'}
    if hasattr(e,'message_dict') and e.message_dict:
      d['fields'] = e.message_dict
    if hasattr(e,'messages') and e.messages:
      d['messages'] = e.messages
    return HttpResponse(json.dumps(d, ensure_ascii=False), status=400, content_type='application/json;charset=utf-8')

@csrf_exempt
@never_cache
def add(request):
  try:
    addParams = viewutil.request_params(request)
    addtype = addParams['type']
    if not request.user.has_perm('tracker.add_' + permmap.get(addtype,addtype)):
      return HttpResponse('Access denied',status=403,content_type='text/plain;charset=utf-8')
    Model = modelmap[addtype]
    newobj = Model()
    for k,v in addParams.items():
      if k in ('type','id'):
        continue
      if v == 'null':
        v = None
      elif fkmap.get(k,k) in modelmap:
        v = modelmap[fkmap.get(k,k)].objects.get(id=v)
      setattr(newobj,k,v)
    newobj.full_clean()
    newobj.save()
    log.addition(request, newobj)
    resp = HttpResponse(serializers.serialize('json', Model.objects.filter(id=newobj.id), ensure_ascii=False),content_type='application/json;charset=utf-8')
    if 'queries' in request.GET and request.user.has_perm('tracker.view_queries'):
      return HttpResponse(json.dumps(connection.queries, ensure_ascii=False, indent=1),content_type='application/json;charset=utf-8')
    return resp
  except IntegrityError, e:
    return HttpResponse(json.dumps({'error': u'Integrity error: %s' % e}, ensure_ascii=False), status=400, content_type='application/json;charset=utf-8')
  except ValidationError, e:
    d = {'error': u'Validation Error'}
    if hasattr(e,'message_dict') and e.message_dict:
      d['fields'] = e.message_dict
    if hasattr(e,'messages') and e.messages:
      d['messages'] = e.messages
    return HttpResponse(json.dumps(d, ensure_ascii=False), status=400, content_type='application/json;charset=utf-8')
  except KeyError, e:
    return HttpResponse(json.dumps({'error': 'Key Error, malformed add parameters', 'exception': unicode(e)}, ensure_ascii=False), status=400, content_type='application/json;charset=utf-8')
  except FieldError, e:
    return HttpResponse(json.dumps({'error': 'Field Error, malformed add parameters', 'exception': unicode(e)}, ensure_ascii=False), status=400, content_type='application/json;charset=utf-8')
  except ValueError, e:
    return HttpResponse(json.dumps({'error': u'Value Error', 'exception': unicode(e)}, ensure_ascii=False), status=400, content_type='application/json;charset=utf-8')

@csrf_exempt
@never_cache
def delete(request):
  try:
    deleteParams = viewutil.request_params(request)
    deltype = deleteParams['type']
    if not request.user.has_perm('tracker.delete_' + permmap.get(deltype,deltype)):
      return HttpResponse('Access denied',status=403,content_type='text/plain;charset=utf-8')
    obj = modelmap[deltype].objects.get(pk=deleteParams['id'])
    log.deletion(request, obj)
    obj.delete()
    return HttpResponse(json.dumps({'result': u'Object %s of type %s deleted' % (deleteParams['id'], deleteParams['type'])}, ensure_ascii=False), content_type='application/json;charset=utf-8')
  except IntegrityError, e:
    return HttpResponse(json.dumps({'error': u'Integrity error: %s' % e}, ensure_ascii=False), status=400, content_type='application/json;charset=utf-8')
  except ValidationError, e:
    d = {'error': u'Validation Error'}
    if hasattr(e,'message_dict') and e.message_dict:
      d['fields'] = e.message_dict
    if hasattr(e,'messages') and e.messages:
      d['messages'] = e.messages
    return HttpResponse(json.dumps(d, ensure_ascii=False), status=400, content_type='application/json;charset=utf-8')
  #except KeyError, e:
    return HttpResponse(json.dumps({'error': 'Key Error, malformed delete parameters', 'exception': unicode(e)}, ensure_ascii=False), status=400, content_type='application/json;charset=utf-8')
  except ObjectDoesNotExist, e:
    return HttpResponse(json.dumps({'error': 'Object does not exist'}, ensure_ascii=False), status=400, content_type='application/json;charset=utf-8')

@csrf_exempt
@never_cache
def edit(request):
  try:
    editParams = viewutil.request_params(request)
    edittype = editParams['type']
    if not request.user.has_perm('tracker.change_' + permmap.get(edittype,edittype)):
      return HttpResponse('Access denied',status=403,content_type='text/plain;charset=utf-8')
    Model = modelmap[edittype]
    obj = Model.objects.get(pk=editParams['id'])
    changed = []
    for k,v in editParams.items():
      if k in ('type','id'): continue
      if v == 'None':
        v = None
      elif fkmap.get(k,k) in modelmap:
        v = modelmap[fkmap.get(k,k)].objects.get(id=v)
      if unicode(getattr(obj,k)) != unicode(v):
        changed.append(k)
      setattr(obj,k,v)
    obj.full_clean()
    obj.save()
    if changed:
      log.change(request,obj,u'Changed field%s %s.' % (len(changed) > 1 and 's' or '', ', '.join(changed)))
    resp = HttpResponse(serializers.serialize('json', Model.objects.filter(id=obj.id), ensure_ascii=False),content_type='application/json;charset=utf-8')
    if 'queries' in request.GET and request.user.has_perm('tracker.view_queries'):
      return HttpResponse(json.dumps(connection.queries, ensure_ascii=False, indent=1),content_type='application/json;charset=utf-8')
    return resp
  except IntegrityError, e:
    return HttpResponse(json.dumps({'error': u'Integrity error: %s' % e}, ensure_ascii=False), status=400, content_type='application/json;charset=utf-8')
  except ValidationError, e:
    d = {'error': u'Validation Error'}
    if hasattr(e,'message_dict') and e.message_dict:
      d['fields'] = e.message_dict
    if hasattr(e,'messages') and e.messages:
      d['messages'] = e.messages
    return HttpResponse(json.dumps(d, ensure_ascii=False), status=400, content_type='application/json;charset=utf-8')
  except KeyError, e:
    return HttpResponse(json.dumps({'error': 'Key Error, malformed edit parameters', 'exception': unicode(e)}, ensure_ascii=False), status=400, content_type='application/json;charset=utf-8')
  except FieldError, e:
    return HttpResponse(json.dumps({'error': 'Field Error, malformed edit parameters', 'exception': unicode(e)}, ensure_ascii=False), status=400, content_type='application/json;charset=utf-8')
  except ValueError, e:
    return HttpResponse(json.dumps({'error': u'Value Error: %s' % e}, ensure_ascii=False), status=400, content_type='application/json;charset=utf-8')

def bidindex(request, event=None):
  event = viewutil.get_event(event)
  searchForm = BidSearchForm(request.GET)
  if not searchForm.is_valid():
    return HttpResponse('Invalid filter form', status=400)
  searchParams = {}
  searchParams.update(request.GET)
  searchParams.update(searchForm.cleaned_data)
  if event.id:
    searchParams['event'] = event.id
  else:
    return HttpResponseRedirect('/tracker')
  bids = filters.run_model_query('bid', searchParams, user=request.user)
  bids = bids.filter(parent=None)
  total = bids.aggregate(Sum('total'))['total__sum'] or Decimal('0.00')
  choiceTotal = bids.filter(goal=None).aggregate(Sum('total'))['total__sum'] or Decimal('0.00')
  challengeTotal = bids.exclude(goal=None).aggregate(Sum('total'))['total__sum'] or Decimal('0.00')
  bids = viewutil.get_tree_queryset_descendants(Bid, bids, include_self=True).prefetch_related('options')
  bids = bids.filter(parent=None)
  if event.id:
    bidNameSpan = 2
  else:
    bidNameSpan = 1
  return tracker_response(request, 'tracker/bidindex.html', { 'searchForm': searchForm, 'bids': bids, 'total': total, 'event': event, 'bidNameSpan' : bidNameSpan, 'choiceTotal': choiceTotal, 'challengeTotal': challengeTotal })

def bid(request, id):
  try:
    orderdict = {
      'name'   : ('donation__donor__lastname', 'donation__donor__firstname'),
      'amount' : ('amount', ),
      'time'   : ('donation__timereceived', ),
    }
    sort = request.GET.get('sort', 'time')
    if sort not in orderdict:
      sort = 'time'
    try:
      order = int(request.GET.get('order', '-1'))
    except ValueError:
      order = -1
    bid = Bid.objects.get(pk=id)
    bids = bid.get_descendants(include_self=True).select_related('speedrun','event', 'parent').prefetch_related('options')
    ancestors = bid.get_ancestors()
    event = bid.event if bid.event else bid.speedrun.event
    if not bid.istarget:
      return tracker_response(request, 'tracker/bid.html', { 'event': event, 'bid' : bid, 'ancestors' : ancestors })
    else:
      donationBids = DonationBid.objects.filter(bid__exact=id).filter(viewutil.DonationBidAggregateFilter)
      donationBids = donationBids.select_related('donation','donation__donor').order_by('-donation__timereceived')
      donationBids = fixorder(donationBids, orderdict, sort, order)
      comments = 'comments' in request.GET
      return tracker_response(request, 'tracker/bid.html', { 'event': event, 'bid' : bid, 'comments' : comments, 'donationBids' : donationBids, 'ancestors' : ancestors })
  except Bid.DoesNotExist:
    return tracker_response(request, template='tracker/badobject.html', status=404)

def donorindex(request,event=None):
  event = viewutil.get_event(event)
  orderdict = {
    'name'  : ('donor__lastname', 'donor__firstname'),
    'total' : ('donation_total',    ),
    'max'   : ('donation_max',      ),
    'avg'   : ('donation_avg',      )
  }
  page = request.GET.get('page', 1)
  sort = request.GET.get('sort', 'name')
  if sort not in orderdict:
    sort = 'name'
  try:
    order = int(request.GET.get('order', 1))
  except ValueError:
    order = 1

  donors = DonorCache.objects.filter(event=event.id if event.id else None).order_by(*orderdict[sort])
  if order == -1:
    donors = donors.reverse()

  fulllist = request.user.has_perm('tracker.view_full_list') and page == 'full'
  pages = Paginator(donors,50)

  if fulllist:
    pageinfo = { 'paginator' : pages, 'has_previous' : False, 'has_next' : False, 'paginator.num_pages' : pages.num_pages }
    page = 0
  else:
    try:
      pageinfo = pages.page(page)
    except paginator.PageNotAnInteger:
      pageinfo = pages.page(1)
    except paginator.EmptyPage:
      pageinfo = pages.page(pages.num_pages)
      page = pages.num_pages
    donors = pageinfo.object_list

  return tracker_response(request, 'tracker/donorindex.html', { 'donors' : donors, 'event' : event, 'pageinfo' : pageinfo, 'page' : page, 'fulllist' : fulllist, 'sort' : sort, 'order' : order })

def donor(request,id,event=None):
  try:
    event = viewutil.get_event(event)
    donor = DonorCache.objects.get(donor=id,event=event.id if event.id else None)
    donations = donor.donation_set.filter(transactionstate='COMPLETED')
    if event.id:
      donations = donations.filter(event=event)
    comments = 'comments' in request.GET
    return tracker_response(request, 'tracker/donor.html', { 'donor' : donor, 'donations' : donations, 'comments' : comments, 'event' : event })
  except DonorCache.DoesNotExist:
    return tracker_response(request, template='tracker/badobject.html', status=404)

@cache_page(15) # 15 seconds
def donationindex(request,event=None):
  event = viewutil.get_event(event)
  orderdict = {
    'name'   : ('donor__lastname', 'donor__firstname'),
    'amount' : ('amount', ),
    'time'   : ('timereceived', ),
  }
  page = request.GET.get('page', 1)
  sort = request.GET.get('sort', 'time')
  if sort not in orderdict:
    sort = 'time'
  try:
    order = int(request.GET.get('order', -1))
  except ValueError:
    order = -1
  searchForm = DonationSearchForm(request.GET)
  if not searchForm.is_valid():
    return HttpResponse('Invalid Search Data', status=400)
  searchParams = {}
  searchParams.update(request.GET)
  searchParams.update(searchForm.cleaned_data)
  if event.id:
    searchParams['event'] = event.id
  donations = filters.run_model_query('donation', searchParams, user=request.user)
  donations = fixorder(donations, orderdict, sort, order)
  fulllist = request.user.has_perm('tracker.view_full_list') and page == 'full'
  pages = Paginator(donations,50)
  if fulllist:
    pageinfo = { 'paginator' : pages, 'has_previous' : False, 'has_next' : False, 'paginator.num_pages' : pages.num_pages }
    page = 0
  else:
    try:
      pageinfo = pages.page(page)
    except paginator.PageNotAnInteger:
      pageinfo = pages.page(1)
    except paginator.EmptyPage:
      pageinfo = pages.page(paginator.num_pages)
      page = pages.num_pages
    donations = pageinfo.object_list
  agg = donations.aggregate(amount=Sum('amount'), count=Count('amount'), max=Max('amount'), avg=Avg('amount'))
  return tracker_response(request, 'tracker/donationindex.html', { 'searchForm': searchForm, 'donations' : donations, 'pageinfo' :  pageinfo, 'page' : page, 'fulllist' : fulllist, 'agg' : agg, 'sort' : sort, 'order' : order, 'event': event })

def donation(request,id):
  try:
    donation = Donation.objects.get(pk=id)
    if donation.transactionstate != 'COMPLETED':
      return tracker_response(request, 'tracker/badobject.html')
    event = donation.event
    donor = donation.donor
    donationbids = DonationBid.objects.filter(donation=id).select_related('bid','bid__speedrun','bid__event')
    return tracker_response(request, 'tracker/donation.html', { 'event': event, 'donation' : donation, 'donor' : donor, 'donationbids' : donationbids })
  except Donation.DoesNotExist:
    return tracker_response(request, template='tracker/badobject.html', status=404)

def runindex(request,event=None):
  event = viewutil.get_event(event)
  searchForm = RunSearchForm(request.GET)
  if not searchForm.is_valid():
    return HttpResponse('Invalid Search Data', status=400)
  searchParams = {}
  searchParams.update(request.GET)
  searchParams.update(searchForm.cleaned_data)
  if event.id:
    searchParams['event'] = event.id
  runs = filters.run_model_query('run', searchParams, user=request.user)
  runs = runs.select_related('runners').annotate(hasbids=Sum('bids'))
  return tracker_response(request, 'tracker/runindex.html', { 'searchForm': searchForm, 'runs' : runs, 'event': event })

def run(request,id):
  try:
    run = SpeedRun.objects.get(pk=id)
    runners = run.runners.all()
    event = run.event
    bids = filters.run_model_query('bid', {'run': id}, user=request.user)
    bids = viewutil.get_tree_queryset_descendants(Bid, bids, include_self=True).select_related('speedrun','event', 'parent').prefetch_related('options')
    topLevelBids = filter(lambda bid: bid.parent == None, bids)
    bids = topLevelBids

    return tracker_response(request, 'tracker/run.html', { 'event': event, 'run' : run, 'runners': runners, 'bids' : topLevelBids })
  except SpeedRun.DoesNotExist:
    return tracker_response(request, template='tracker/badobject.html', status=404)

def prizeindex(request,event=None):
  event = viewutil.get_event(event)
  searchForm = PrizeSearchForm(request.GET)
  if not searchForm.is_valid():
    return HttpResponse('Invalid Search Data', status=400)
  searchParams = {}
  searchParams.update(request.GET)
  searchParams.update(searchForm.cleaned_data)
  if event.id:
    searchParams['event'] = event.id
  prizes = filters.run_model_query('prize', searchParams, user=request.user)
  prizes = prizes.select_related('startrun','endrun','category').prefetch_related('prizewinner_set')
  return tracker_response(request, 'tracker/prizeindex.html', { 'searchForm': searchForm, 'prizes' : prizes, 'event': event })

def prize(request,id):
  try:
    prize = Prize.objects.get(pk=id)
    event = prize.event
    games = None
    category = None
    if prize.startrun:
      games = SpeedRun.objects.filter(starttime__gte=SpeedRun.objects.get(pk=prize.startrun.id).starttime,endtime__lte=SpeedRun.objects.get(pk=prize.endrun.id).endtime)
    if prize.category:
      category = PrizeCategory.objects.get(pk=prize.category.id)
    return tracker_response(request, 'tracker/prize.html', { 'event': event, 'prize' : prize, 'games' : games,  'category': category })
  except Prize.DoesNotExist:
    return tracker_response(request, template='tracker/badobject.html', status=404)

@never_cache
def prize_donors(request):
  try:
    if not request.user.has_perm('tracker.change_prize'):
      return HttpResponse('Access denied',status=403,content_type='text/plain;charset=utf-8')
    requestParams = viewutil.request_params(request)
    id = int(requestParams['id'])
    resp = HttpResponse(json.dumps(Prize.objects.get(pk=id).eligible_donors()),content_type='application/json;charset=utf-8')
    if 'queries' in request.GET and request.user.has_perm('tracker.view_queries'):
      return HttpResponse(json.dumps(connection.queries, ensure_ascii=False, indent=1),content_type='application/json;charset=utf-8')
    return resp
  except Prize.DoesNotExist:
    return HttpResponse(json.dumps({'error': 'Prize id does not exist'}),status=404,content_type='application/json;charset=utf-8')

@csrf_exempt
@never_cache
def draw_prize(request):
  try:
    if not request.user.has_perm('tracker.change_prize'):
      return HttpResponse('Access denied',status=403,content_type='text/plain;charset=utf-8')

    requestParams = viewutil.request_params(request)

    id = int(requestParams['id'])

    prize = Prize.objects.get(pk=id)

    if prize.maxed_winners():
      maxWinnersMessage = "Prize: " + prize.name + " already has a winner." if prize.maxwinners == 1 else "Prize: " + prize.name + " already has the maximum number of winners allowed."
      return HttpResponse(json.dumps({'error': maxWinnersMessage}),status=409,content_type='application/json;charset=utf-8')


    skipKeyCheck = requestParams.get('skipkey', False)

    if not skipKeyCheck:
      eligible = prize.eligible_donors()
      if not eligible:
        return HttpResponse(json.dumps({'error': 'Prize has no eligible donors'}),status=409,content_type='application/json;charset=utf-8')
      key = hash(json.dumps(eligible))
      if 'key' not in requestParams:
        return HttpResponse(json.dumps({'key': key}),content_type='application/json;charset=utf-8')
      else:
        try:
          okey = type(key)(requestParams['key'])
        except (ValueError,KeyError),e:
          return HttpResponse(json.dumps({'error': 'Key field was missing or malformed', 'exception': '%s %s' % (type(e),e)},ensure_ascii=False),status=400,content_type='application/json;charset=utf-8')

    if 'queries' in request.GET and request.user.has_perm('tracker.view_queries'):
      return HttpResponse(json.dumps(connection.queries, ensure_ascii=False, indent=1),content_type='application/json;charset=utf-8')

    limit = requestParams.get('limit', prize.maxwinners)
    if not limit:
      limit = prize.maxwinners

    currentCount = prize.current_win_count()
    status = True
    results = []
    while status and currentCount < limit:
      status, data = viewutil.draw_prize(prize, seed=requestParams.get('seed',None))
      if status:
        currentCount += 1
        results.append(data)
        log.change(request,prize,u'Picked winner. %.2f,%.2f' % (data['sum'],data['result']))
        return HttpResponse(json.dumps({'success': results}, ensure_ascii=False),content_type='application/json;charset=utf-8')
      else:
        return HttpResponse(json.dumps(data),status=400,content_type='application/json;charset=utf-8')
  except Prize.DoesNotExist:
    return HttpResponse(json.dumps({'error': 'Prize id does not exist'}),status=404,content_type='application/json;charset=utf-8')

@csrf_exempt
def submit_prize(request, event):
  event = viewutil.get_event(event)
  if request.method == 'POST':
    prizeForm = PrizeSubmissionForm(data=request.POST)
    if prizeForm.is_valid():
      prize = Prize.objects.create(
        event=event,
        name=prizeForm.cleaned_data['name'],
        description=prizeForm.cleaned_data['description'],
        maxwinners=prizeForm.cleaned_data['maxwinners'],
        extrainfo=prizeForm.cleaned_data['extrainfo'],
        estimatedvalue=prizeForm.cleaned_data['estimatedvalue'],
        minimumbid=prizeForm.cleaned_data['suggestedamount'],
        maximumbid=prizeForm.cleaned_data['suggestedamount'],
        image=prizeForm.cleaned_data['imageurl'],
        provided=prizeForm.cleaned_data['providername'],
        provideremail=prizeForm.cleaned_data['provideremail'],
        creator=prizeForm.cleaned_data['creatorname'],
        creatoremail=prizeForm.cleaned_data['creatoremail'],
        creatorwebsite=prizeForm.cleaned_data['creatorwebsite'],
        startrun=prizeForm.cleaned_data['startrun'],
        endrun=prizeForm.cleaned_data['endrun'])
      prize.save()
      return tracker_response(request, "tracker/submit_prize_success.html", { 'prize': prize })
  else:
    prizeForm = PrizeSubmissionForm()

  runs = filters.run_model_query('run', {'event': event}, request.user)

  def run_info(run):
    return {'id': run.id, 'name': run.name, 'description': run.description, 'runners': run.deprecated_runners, 'starttime': run.starttime.isoformat(), 'endtime': run.endtime.isoformat() }

  dumpArray = [run_info(o) for o in runs.all()]
  runsJson = json.dumps(dumpArray)

  return tracker_response(request, "tracker/submit_prize_form.html", { 'event': event, 'form': prizeForm, 'runs': runsJson })

@never_cache
def merge_schedule(request,id):
  if not request.user.has_perm('tracker.sync_schedule'):
    return tracker_response(request, template='404.html', status=404)
  try:
    event = Event.objects.get(pk=id)
  except Event.DoesNotExist:
    return tracker_response(request, template='tracker/badobject.html', status=404)
  try:
    numRuns = viewutil.merge_schedule_gdoc(event)
  except Exception as e:
    return HttpResponse(json.dumps({'error': e.message }),status=500,content_type='application/json;charset=utf-8')

  return HttpResponse(json.dumps({'result': 'Merged %d run(s)' % numRuns }),content_type='application/json;charset=utf-8')

@never_cache
@csrf_exempt
def refresh_schedule(request):
  from django.contrib.auth.models import User
  try:
    id, username = request.META['HTTP_X_GOOG_CHANNEL_TOKEN'].split(':')
    event = Event.objects.get(id=id)
  except (ValueError, Event.DoesNotExist):
    return HttpResponse(json.dumps({'result': 'Event not found'}), status=404, content_type='application/json;charset=utf-8')
  viewutil.merge_schedule_gdoc(event, username)
  viewutil.tracker_log(u'schedule', u'Merged schedule via push for event {0}'.format(event), event=event,
                       user=User.objects.filter(username=username).first())
  return HttpResponse(json.dumps({'result': 'Merged successfully'}), content_type='application/json;charset=utf-8')

@csrf_exempt
def paypal_cancel(request):
  return tracker_response(request, "tracker/paypal_cancel.html")

@csrf_exempt
def paypal_return(request):
  return tracker_response(request, "tracker/paypal_return.html")

@transaction.commit_on_success
@csrf_exempt
def donate(request, event):
  event = viewutil.get_event(event)
  if event.locked:
    raise Http404
  bidsFormPrefix = "bidsform"
  prizeFormPrefix = "prizeForm"
  if request.method == 'POST':
    commentform = DonationEntryForm(data=request.POST)
    if commentform.is_valid():
      prizesform = PrizeTicketFormSet(amount=commentform.cleaned_data['amount'], data=request.POST, prefix=prizeFormPrefix)
      bidsform = DonationBidFormSet(amount=commentform.cleaned_data['amount'], data=request.POST, prefix=bidsFormPrefix)
      if bidsform.is_valid() and prizesform.is_valid():
        try:
          donation = Donation(amount=commentform.cleaned_data['amount'], timereceived=pytz.utc.localize(datetime.datetime.utcnow()), domain='PAYPAL', domainId=str(random.getrandbits(128)), event=event, testdonation=event.usepaypalsandbox)
          if commentform.cleaned_data['comment']:
            donation.comment = commentform.cleaned_data['comment']
            donation.commentstate = "PENDING"
          donation.requestedvisibility = commentform.cleaned_data['requestedvisibility']
          donation.requestedalias = commentform.cleaned_data['requestedalias']
          donation.requestedemail = commentform.cleaned_data['requestedemail']
          donation.currency = event.paypalcurrency
          donation.save()
          for bidform in bidsform:
            if 'bid' in bidform.cleaned_data and bidform.cleaned_data['bid']:
              bid = bidform.cleaned_data['bid']
              if bid.allowuseroptions:
                # unfortunately, you can't use get_or_create when using a non-atomic transaction
                # this does technically introduce a race condition, I'm just going to hope that two people don't
                # suggest the same option at the exact same time
                # also, I want to do case-insensitive comparison on the name
                try:
                  bid = Bid.objects.get(event=bid.event, speedrun=bid.speedrun, name__iexact=bidform.cleaned_data['customoptionname'], parent=bid)
                except Bid.DoesNotExist:
                  bid = Bid.objects.create(event=bid.event, speedrun=bid.speedrun, name=bidform.cleaned_data['customoptionname'], parent=bid, state='PENDING', istarget=True)
              donation.bids.add(DonationBid(bid=bid, amount=Decimal(bidform.cleaned_data['amount'])))
          for prizeform in prizesform:
            if 'prize' in prizeform.cleaned_data and prizeform.cleaned_data['prize']:
              prize = prizeform.cleaned_data['prize']
              donation.tickets.add(PrizeTicket(prize=prize, amount=Decimal(prizeform.cleaned_data['amount'])))
          donation.full_clean()
          donation.save()
        except Exception as e:
          transaction.rollback()
          raise e

        serverURL = viewutil.get_request_server_url(request)

        paypal_dict = {
          "amount": str(donation.amount),
          "cmd": "_donations",
          "business": donation.event.paypalemail,
          "item_name": donation.event.receivername,
          "notify_url": serverURL + reverse('tracker.views.ipn'),
          "return_url": serverURL + reverse('tracker.views.paypal_return'),
          "cancel_return": serverURL + reverse('tracker.views.paypal_cancel'),
          "custom": str(donation.id) + ":" + donation.domainId,
          "currency_code": donation.event.paypalcurrency,
        }
        # Create the form instance
        form = PayPalPaymentsForm(button_type="donate", sandbox=donation.event.usepaypalsandbox, initial=paypal_dict)
        context = {"event": donation.event, "form": form }
        return tracker_response(request, "tracker/paypal_redirect.html", context)
    else:
      bidsform = DonationBidFormSet(amount=Decimal('0.00'), data=request.POST, prefix=bidsFormPrefix)
      prizesform = PrizeTicketFormSet(amount=Decimal('0.00'), data=request.POST, prefix=prizeFormPrefix)
  else:
    commentform = DonationEntryForm()
    bidsform = DonationBidFormSet(amount=Decimal('0.00'), prefix=bidsFormPrefix)
    prizesform = PrizeTicketFormSet(amount=Decimal('0.00'), prefix=prizeFormPrefix)

  def bid_parent_info(bid):
    if bid != None:
      return {'name': bid.name, 'description': bid.description, 'parent': bid_parent_info(bid.parent) }
    else:
      return None

  def bid_info(bid):
    result = {
      'id': bid.id,
      'name': bid.name,
      'description': bid.description,
      'label': bid.full_label(not bid.allowuseroptions),
      'count': bid.count,
      'amount': bid.total,
      'goal': Decimal(bid.goal or '0.00'),
      'parent': bid_parent_info(bid.parent)
    }
    if bid.speedrun:
      result['runname'] = bid.speedrun.name
    if bid.suggestions.exists():
      result['suggested'] = list(map(lambda x: x.name, bid.suggestions.all()))
    if bid.allowuseroptions:
      result['custom'] = ['custom']
      result['label'] += ' (select and add a name next to "New Option Name")'
    return result

  bids = filters.run_model_query('bidtarget', {'state':'OPENED', 'event':event.id }, user=request.user).distinct().select_related('parent').prefetch_related('suggestions')

  allPrizes = filters.run_model_query('prize', {'feed': 'current', 'event': event.id })

  prizes = allPrizes.filter(ticketdraw=False)

  dumpArray = [bid_info(o) for o in bids]
  bidsJson = json.dumps(dumpArray)

  ticketPrizes = allPrizes.filter(ticketdraw=True)

  def prize_info(prize):
    result = {'id': prize.id, 'name': prize.name, 'description': prize.description, 'minimumbid': prize.minimumbid, 'maximumbid': prize.maximumbid}
    return result

  dumpArray = [prize_info(o) for o in ticketPrizes.all()]
  ticketPrizesJson = json.dumps(dumpArray)

  return tracker_response(request, "tracker/donate.html", { 'event': event, 'bidsform': bidsform, 'prizesform': prizesform, 'commentform': commentform, 'hasBids': bids.count() > 0, 'bidsJson': bidsJson, 'hasTicketPrizes': ticketPrizes.count() > 0, 'ticketPrizesJson': ticketPrizesJson, 'prizes': prizes})

@csrf_exempt
@never_cache
def ipn(request):
  donation = None
  ipnObj = None

  if request.method == 'GET' or len(request.POST) == 0:
    return tracker_response(request, "tracker/badobject.html", {})

  try:
    ipnObj = paypalutil.create_ipn(request)
    ipnObj.save()

    donation = paypalutil.initialize_paypal_donation(ipnObj)
    donation.save()

    if donation.transactionstate == 'PENDING':
      reasonExplanation, ourFault = paypalutil.get_pending_reason_details(ipnObj.pending_reason)
      if donation.event.pendingdonationemailtemplate:
        formatContext = {
          'event': donation.event,
          'donation': donation,
          'donor': donor,
          'pending_reason': ipnObj.pending_reason,
          'reason_info': reasonExplanation if not ourFault else '',
        }
        post_office.mail.send(recipients=[donation.donor.email], sender=donation.event.donationemailsender, template=donation.event.pendingdonationemailtemplate, context=formatContext)
      # some pending reasons can be a problem with the receiver account, we should keep track of them
      if ourFault:
        paypalutil.log_ipn(ipnObj, 'Unhandled pending error')
    elif donation.transactionstate == 'COMPLETED':
      if donation.event.donationemailtemplate != None:
        formatContext = {
          'donation': donation,
          'donor': donation.donor,
          'event': donation.event,
          'prizes': viewutil.get_donation_prize_info(donation),
        }
        post_office.mail.send(recipients=[donation.donor.email], sender=donation.event.donationemailsender, template=donation.event.donationemailtemplate, context=formatContext)

      # TODO: this should eventually share code with the 'search' method, to
      postbackData = {
        'id': donation.id,
        'timereceived': str(donation.timereceived),
        'comment': donation.comment,
        'amount': donation.amount,
        'donor__visibility': donation.donor.visibility,
        'donor__visiblename': donation.donor.visible_name(),
      }
      postbackJSon = json.dumps(postbackData)
      postbacks = PostbackURL.objects.filter(event=donation.event)
      for postback in postbacks:
        opener = urllib2.build_opener()
        req = urllib2.Request(postback.url, postbackJSon, headers={'Content-Type': 'application/json; charset=utf-8'})
        response = opener.open(req, timeout=5)
    elif donation.transactionstate == 'CANCELLED':
      # eventually we may want to send out e-mail for some of the possible cases
      # such as payment reversal due to double-transactions (this has happened before)
      paypalutil.log_ipn(ipnObj, 'Cancelled/reversed payment')

  except Exception as inst:
    print(inst)
    print(traceback.format_exc(inst))
    if ipnObj:
      paypalutil.log_ipn(ipnObj, "{0} \n {1}. POST data : {2}".format(inst, traceback.format_exc(inst), request.POST))
    else:
      viewutil.tracker_log('paypal', 'IPN creation failed: {0} \n {1}. POST data : {2}'.format(inst, traceback.format_exc(inst), request.POST))

  return HttpResponse("OKAY")


class GraphView(TemplateView):
    template_name = 'tracker/graphindex.html'

    def get_context_data(self, *args, **kwargs):
        context = super(GraphView, self).get_context_data(*args, **kwargs)
        context['event'] = event = viewutil.get_event(kwargs['event'])
        return context

class GraphDataView(View):

    # TODO: Test all times re: relative/timezones 
    binned_datetime_format = '%Y-%m-%d %H:%M:%S'
    point_datetime_format = '%Y-%m-%dT%H:%M:%S+00:00'

    @classmethod
    def extract_donation_schedule(cls, qs, truncate_by=None):
        if not truncate_by:
            raise TypeError('Please provide truncate_by')
        (extra_query, extra_params) = connection.ops.datetime_trunc_sql(truncate_by, 'timereceived', None)
        schedule = qs.extra(select={truncate_by: extra_query}, select_params=extra_params)\
            .order_by()\
            .values(truncate_by)\
            .annotate(count=Count('amount'), total=Sum('amount'))
        return schedule

    def get_data(self, event):

        data = {}

        # TODO: Ordering donations based on timereceived might be an
        # disadvantage people that are slow at clicking through the Paypal
        # interface; add a timecompleted instead?
        all_donations = filters.run_model_query('donation', {'event': event}, user=self.request.user).order_by('-timereceived')

        if not all_donations:
            return data

        try:
            replay_up_to = float(self.request.GET.get('replay', None))
        except TypeError:
            replay_up_to = None

        event_moments = all_donations.aggregate(start=Min('timereceived'), end=Max('timereceived'));

        if replay_up_to:
            reference_moment = event_moments['start'] + datetime.timedelta(seconds=replay_up_to)
        else:
            reference_moment = event_moments['end']
        reference_moment += relativedelta(microsecond=0) # When microseconds are non-zero isoformat() will change

        print('Reference moment set to: ' + reference_moment.isoformat())

        data['reference_moment'] = reference_moment.isoformat()
        donations = all_donations.filter(timereceived__lt=reference_moment)

        data['recent_donations'] = [
            {
                'moment': x.timereceived.isoformat(),
                'amount': x.amount, 
                'donor': x.donor.visible_name()
            } for x in donations[:10]
        ]

        cutoff_24h = reference_moment - relativedelta(hours=24, minute=0, second=0)  # Note: minute and second are *set* to 0

        # Last 24h.
        data['bar_hourly_count'] = {
            'meta': {
                'start': cutoff_24h.isoformat(),
                'end': (reference_moment + relativedelta(hours=1, minute=0, second=0)).isoformat(),
            },
            'data': self.get_context_bar_count_per_hour(donations.filter(timereceived__gt=cutoff_24h))
        }
        print('meta', data['bar_hourly_count']['meta'])

        # When we drop support for Django<1.8 we can use https://docs.djangoproject.com/en/1.8/ref/models/conditional-expressions/ here
        distribution_mapping = [
            (50, 5),    # Everything under $50 is split in bins of $5
            (100, 10),  # Everything under $100 is split in bins of $10
            #(300, 20),  # Everything under $300 is split in bins of $20
        ]
        #distribution_mapping = [
        #    (300, 1),
        #]
        distribution_graph = donations.filter(timereceived__gt=cutoff_24h).order_by().values('amount').annotate(count=Count('amount'))
        distribution_bins = {}
        # Pre-defining all bins so that D3 knows where to draw what
        lower_limit = 0
        for (end_value, binsize) in distribution_mapping:
            for lower_limit in range(lower_limit, end_value, binsize):
                distribution_bins[(lower_limit, lower_limit + binsize)] = 0
                lower_limit = end_value
        distribution_bins[(end_value, -1)] = 0  # Everything about end_value

        # Put 13 donations for 13 dollar into the bin (10, 15) etc:
        # TODO: Use distribution_mapping
        for distribution_size in distribution_graph:
            #if distribution_size['amount'] < 300:
            #    distribution_bins[(int(distribution_size['amount']), int(distribution_size['amount']) + 1)] += distribution_size['count']
            #else:
            #    distribution_bins[(300, -1)] += distribution_size['count']
            if distribution_size['amount'] < 50:
                lower_five = int(distribution_size['amount']) / 5 * 5
                upper_five = lower_five + 5
                distribution_bins[(lower_five, upper_five)] += distribution_size['count']
            elif distribution_size['amount'] < 100:
                lower_ten = int(distribution_size['amount']) / 10 * 10
                upper_ten= lower_ten + 10
                distribution_bins[(lower_ten, upper_ten)] += distribution_size['count']
            #elif distribution_size['amount'] < 300:
            #    lower_twenty = int(distribution_size['amount']) / 20 * 20
            #    upper_twenty = lower_twenty + 20
            #    distribution_bins[(lower_twenty, upper_twenty)] += distribution_size['count']
            else:
                distribution_bins[(100, -1)] += distribution_size['count']

        data['bardistribution'] = [
            {'lower': lower, 'upper': upper, 'count': count} for ((lower, upper), count) in distribution_bins.iteritems()
        ]

        data['aggregated'] = donations.aggregate(amount=Sum('amount'), count=Count('amount'), max=Max('amount'), avg=Avg('amount'))

        # TODO: Configure in admin per event, probably.
        data['event'] = all_donations.aggregate(_start=Min('timereceived'), _end=Max('timereceived'))
        data['event']['start'] = data['event']['_start'].isoformat()
        data['event']['end'] = data['event']['_end'].isoformat()
        event_span = data['event']['_end'] - data['event']['_start']
        data['event']['point_0'] = (event_span / 4 * 1).total_seconds()
        data['event']['point_1'] = (event_span / 4 * 2).total_seconds()
        data['event']['point_2'] = (event_span / 4 * 3).total_seconds()

        # Returning every single donations results in way too many data points
        # on the graph, so we'll bin the values, The graph is 1000 pixels wide
        # and an event takes about 10000 minutes, so if we bin per hour we get
        # about 1 data point per pixel, more than enough with some nice interpolation.
        #
        # For the prettiest plot we have to make sure we start graphing at 0.

        zero_point = {
            # Note: minute and second are *set* to zero
            'moment': (data['event']['_start'] - relativedelta(hours=1, minute=0, second=0)).strftime(self.binned_datetime_format),
            'amount': 0,
            'count': 0,
        }

        running_total_graph = self.extract_donation_schedule(donations, truncate_by='hour')
        data['running_total'] = [zero_point] + [
            {'moment': x['hour'], 'amount': x['total'], 'count': x['count']}
            for x in running_total_graph
        ]

        # TODO: Make dynamic (admin?)
        data['historic_events'] = [
            {'name': 'Classic Games Done Quick', 'amount': 10531.64, 'count': 464},
            {'name': 'AGDQ 2011', 'amount': 52519.83, 'count': 3253},
            #{'name': 'Japan Relief Done Quick', 'amount': 25800.33, 'count': 1192},
            {'name': 'SGDQ 2011', 'amount': 21396.76, 'count': 1118},
            {'name': 'AGDQ 2012', 'amount': 149044.99, 'count': 5872},
            {'name': 'SGDQ 2012', 'amount': 46278.99, 'count': 2207},
            #{'name': 'Spooktacular', 'amount': 9732.99, 'count': 525},
            {'name': 'AGDQ 2013', 'amount': 448425.27, 'count': 16308},
            {'name': 'SGDQ 2013', 'amount': 257181.07, 'count': 10781},
            {'name': 'AGDQ 2014', 'amount': 1031665.50, 'count': 28100},
            {'name': 'SGDQ 2014', 'amount': 718235.07, 'count': 19104},
            {'name': 'AGDQ 2015', 'amount': 1576085.00, 'count': 39501},
            {'name': 'SGDQ 2015', 'amount': 1215700.34, 'count': 28528},
        ]

        del data['event']['_start']
        del data['event']['_end']

        return data

    def get_context_bar_count_per_hour(self, donations):
        hourly_graph = self.extract_donation_schedule(donations, truncate_by='hour')
        return [
            {'moment': x['hour'], 'total': x['total'], 'count': x['count']}
            for x in hourly_graph
        ]

    def get(self, request, event=None):
        event = viewutil.get_event(event)
        return HttpResponse(
            json.dumps(self.get_data(event)),
            content_type='application/json',
        )

# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import logging
import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django_mailbox.models import Message
from django.utils.datastructures import MultiValueDict
from django.utils.encoding import force_text
from django.utils.translation import ugettext_lazy as _

from postman.models import Message as PostmanMessage
from postman.utils import format_subject

from cosinnus.core.mail import send_mail_or_fail_threaded
from cosinnus_message.forms import CustomReplyForm
from cosinnus.models.group import CosinnusPortal

logger = logging.getLogger('cosinnus')


DIRECT_REPLY_ADDRESSEE = re.compile(r'directreply\+([0-9]+)\+([a-zA-Z0-9]+)@', re.IGNORECASE)
EMAIL_RE = re.compile(
    r"([-!#$%&'*+/=?^_`{}|~0-9A-Z]+(\.[-!#$%&'*+/=?^_`{}|~0-9A-Z]+)*"  # dot-atom
    r'|^"([\001-\010\013\014\016-\037!#-\[\]-\177]|\\[\001-011\013\014\016-\177])*"' # quoted-string
    r')@(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?', re.IGNORECASE)  # domain


def process_direct_reply_messages():
    """ Will check all existing django_mail Messages:
        - drop all mail not containing this Pattern in the body text: directreply+<portal-id>+<hash>@<mailbox-domain> 
        - take all mail for this portal. 
            - if there is a hash matching a postman message, match sender to user, reply as that user using body text
            - delete the mail, no matter if a match was found or not
        - retain the rest (other portals might be using the same mailbox)
        """
    USER_MODEL = get_user_model()
    all_messages = Message.objects.all()
    messages_to_delete = []
    
    for message in all_messages:
        match = DIRECT_REPLY_ADDRESSEE.search(message.text)
        if not match or not len(match.groups()) == 2:
            # message is spam or unrelated to direct messages: remove it
            messages_to_delete.append(message)
            continue
        
        portal_id, hash = match.groups()
        portal_id = int(portal_id)
        hash = hash.lower()
        if not portal_id == CosinnusPortal.get_current().id:
            # message is not for this portal, retain message for other portals
            continue
        
        # from now we either process the message or not, but we definitely delete it, so:
        messages_to_delete.append(message)
        
        # try to find a postman message with the hash from this addressee
        try:
            postman_message = PostmanMessage.objects.get(direct_reply_hash=hash)
        except PostmanMessage.DoesNotExist:
            continue
            
        # try to find the sender email in the user accounts
        sender_email_bad = False
        try:
            from_email_match = EMAIL_RE.search(message.from_header)
            if not from_email_match or not from_email_match.group(): 
                continue
            replier_email = from_email_match.group()
            user = USER_MODEL.objects.get(is_active=True, email__iexact=replier_email)
        except USER_MODEL.DoesNotExist:
            sender_email_bad = True
        
        # get and clean message body
        text = message.text or ''
        text = clean_reply_message_quotation(text)
        
        # make sure the sender of the reply is really the recipient of the replied-to message!
        # if this doesn't match, likely a valid user just replied from the wrong email account, so we send them an error message back
        if sender_email_bad or not user == postman_message.recipient:
            send_direct_reply_error_mail(replier_email, text, _('The email adress you sent the reply from is not the one associated with your user account. Please send direct replies only from the email adress you are registered with on the site!'))
            continue
        
        # error out on empty texts
        successfully_replied = False
        if text and text.strip():
            # emulate the user sending a postman message
            successfully_replied = reply_to_postman_message(postman_message, user, text)
        
        if not successfully_replied:
            send_direct_reply_error_mail(replier_email, text, _('There was an error when processing your message text!'))
            continue
        logger.info('Direct reply successfully processed.')
        
    if not getattr(settings, 'DEBUG_LOCAL', False):
        Message.objects.filter(id__in=[m.id for m in messages_to_delete]).delete()
   

def clean_reply_message_quotation(text):
    """ Attempts to clean out all previous quoted email fragments from an email text-only body text. """
    had_reply = False
    
    lines = text.split('\n')
    clean_lines = []
    
    # aggressively remove all lines after the first reply-quote character
    for line in lines:
        if line.startswith('>'):
            break
        clean_lines.append(line)
    
    if len(clean_lines) < lines:
        # we have removed a reply, mark this!
        had_reply = True
        
    # remove empty beginning and trailing lines
    def _remove_empty_trailing_lines_till_text(_lines):
        if not _lines: return _lines
        for index in reversed(xrange(len(_lines))):
            if len(_lines[index].strip()) == 0:
                del _lines[index]
            else:
                break
        return _lines
    clean_lines = _remove_empty_trailing_lines_till_text(clean_lines)
    clean_lines = list(reversed(_remove_empty_trailing_lines_till_text(list(reversed(clean_lines)))))
    
    # if we removed a reply, we may now delete the last line, if it ends with a ':'
    # that is the gmail client way of saying "On <date>, <sender> wrote:"
    if clean_lines and had_reply:
        if clean_lines[-1].strip().endswith(':'):
            del clean_lines[-1]
            clean_lines = _remove_empty_trailing_lines_till_text(clean_lines)
    
    text = '\n'.join(clean_lines) 
    return text
    
    
def reply_to_postman_message(message, user, text):    
    """ Sends a reply to a postman message with a given text, from a given user.
        @param message: The postman message to reply to (usually the last message in the thread that is not from `user`)
        @param user: The replying user as User model 
        @param text: The text-only body text of the reply. 
        @param return:  """
    kwargs = {
       'initial': {},
       'recipient': message.sender,
       'sender': user,
       'site': CosinnusPortal.get_current().site,
       'data': MultiValueDict({
           'body': [text],
           'subject': message.quote(format_subject)['subject'],
       }),
        
    }
    form = CustomReplyForm(**kwargs)
    if form.is_valid():
        form.save(parent=message)
        return True
    else:
        logger.warning('Could not direct-reply to a postman message, because the form was invalid!', extra={'form-errors': force_text(form.errors), 'wechange-user-email': user.email, 'text': text})
        return False
    
    
def send_direct_reply_error_mail(recipient_email, text, reason):
    subject = _('Your direct reply failed!')
    template = 'cosinnus_message/email_direct_reply_failed.txt'
    send_mail_or_fail_threaded(recipient_email, subject, template, {'reason': reason, 'text': text})

import csv
import errno
import os
import re
import shutil
import zipfile

from cosinnus.utils.urls import group_aware_reverse
from django.db.models import Q, F
from django.contrib.auth import get_user_model
from django.http.response import HttpResponse
from django.template.defaultfilters import slugify
from rest_framework.views import APIView

from postman.models import Message, STATUS_ACCEPTED


class MessageExportView(APIView):

    def _get_users(self, user_ids=None):
        """
        Return users
        :return:
        """
        users = []
        qs = get_user_model().objects.filter(is_active=True)
        if user_ids:
            qs = qs.filter(id__in=user_ids)

        for user in qs:
            users.append([user.id, user.email, user.get_full_name()])
        return users

    def _get_channels(self, user_ids):
        """
        Return channels
        :param user_ids:
        :return:
        """
        channels = []
        qs = Message.objects.filter(
            sender__in=user_ids,
            #sender_archived=False,
            #recipient_archived=False,
            moderation_status=STATUS_ACCEPTED,
            parent__isnull=True,
        )
        qs = qs.exclude(sender_deleted_at__isnull=False, recipient_deleted_at__isnull=False)
        qs = qs.filter(Q(multi_conversation__isnull=True, thread__isnull=True) |
                       Q(multi_conversation__isnull=True, thread_id=F('id')) |
                       Q(multi_conversation__isnull=False, master_for_sender=True, thread__isnull=True) |
                       Q(multi_conversation__isnull=False, master_for_sender=True, thread_id=F('id')))
        for message in qs:
            participants, level = None, None
            if message.multi_conversation:
                participants = ';'.join(str(u.id)
                                        for u in message.multi_conversation.participants.all() if u.id in user_ids)
                if participants:
                    channel_name = f'{slugify(message.subject)}-{message.id}'
                    channels.append([message.id, channel_name, message.sender_id, 'private', participants])
            elif message.sender_id in user_ids and message.recipient_id in user_ids:

                channel_name = slugify(f'{message.sender_id} x {message.recipient_id}')
                channels.append([message.id, channel_name, str(message.sender_id), 'direct', str(message.recipient_id)])
        return channels

    def format_message(self, text):
        """
        Replace WECHANGE formatting language with Rocket.Chat formatting language:
        Rocket.Chat:
            Bold: *Lorem ipsum dolor* ;
            Italic: _Lorem ipsum dolor_ ;
            Strike: ~Lorem ipsum dolor~ ;
            Inline code: `Lorem ipsum dolor`;
            Image: ![Alt text](https://rocket.chat/favicon.ico) ;
            Link: [Lorem ipsum dolor](https://www.rocket.chat/) or <https://www.rocket.chat/ |Lorem ipsum dolor> ;
        :param text:
        :return:
        """
        # Unordered lists: _ to - / * to -
        text = re.sub(r'\n_ ', '\n- ', text)
        text = re.sub(r'\n* ', '\n- ', text)
        # Italic: * to _
        text = re.sub(r'(^|\n|[^\*])\*($|\n|[^\*])', r'\1_\2', text)
        # Bold: ** to *
        text = re.sub(r'\*\*', '*', text)
        # Strike: ~~ to ~
        text = re.sub(r'~~', '~', text)
        return text

    def _get_messages(self, channel, user_ids):
        """
        Return messages in channel
        :return:
        """
        messages, attachments = [], []
        qs = Message.objects.filter(
            sender__in=user_ids,
            #sender_archived=False,
            #recipient_archived=False,
            moderation_status=STATUS_ACCEPTED,
        )
        qs = qs.exclude(sender_deleted_at__isnull=False, recipient_deleted_at__isnull=False)
        qs = qs.filter(Q(id=channel[0]) |
                       Q(thread_id=channel[0]))
        qs = qs.order_by('sent_at')
        for message in qs:
            text = self.format_message(message.body)
            # if message.thread_id == message.id and message.subject:
            if message.subject:
                text = f"*{message.subject}*\n{text}"
            timestamp = int(message.sent_at.timestamp() * 1000)
            messages.append([message.sender_id, timestamp, text])

            for att in message.attached_objects.all():
                fileentry = att.target_object
                attachments.append([
                    message.sender_id,
                    timestamp,
                    group_aware_reverse('cosinnus:file:rocket-download', kwargs={'group': fileentry.group,
                                                                                 'slug': att.target_object.slug})
                ])
        return messages, attachments

    def make_archive(self, file_list, archive, root):
        """
        'fileList' is a list of file names - full path each name
        'archive' is the file name for the archive with a full path
        """
        zip_file = zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED)

        for f in file_list:
            zip_file.write(os.path.join(root, f), f)
        zip_file.close()

    def get(self, request, *args, **kwargs):
        """
        Return users/channels as ZIP file (required by Rocket.Chat)
        see https://rocket.chat/docs/administrator-guides/import/csv/
        :param request:
        :param args:
        :param kwargs:
        :return:
        """
        # Limit to given users, if specified
        users = request.GET.get('users')
        if users:
            users = users.split(',')

        # Recreate folder
        path = 'export'
        if os.path.exists(path) and os.path.isdir(path):
            shutil.rmtree(path)
        if not os.path.exists(path):
            try:
                os.makedirs(path)
            except OSError as exc:  # Guard against race condition
                if exc.errno != errno.EEXIST:
                    raise

        # Create ZIP contents
        users = self._get_users(users)
        with open(f'{path}/users.csv', 'w') as csv_file:
            writer = csv.writer(csv_file, delimiter=',', quoting=csv.QUOTE_ALL)
            writer.writerows(users)
        user_ids = set(u[0] for u in users)

        channels = self._get_channels(user_ids)
        with open(f'{path}/channels.csv', 'w') as csv_file:
            writer = csv.writer(csv_file, delimiter=',', quoting=csv.QUOTE_ALL)
            writer.writerows([channel[1:] for channel in channels])

        for channel in channels:
            messages, attachments = self._get_messages(channel, user_ids)

            if not messages:
                continue
            # Create folder
            channel_path = f'{path}/{channel[1]}'
            if not os.path.exists(channel_path):
                try:
                    os.makedirs(channel_path)
                except OSError as exc:  # Guard against race condition
                    if exc.errno != errno.EEXIST:
                        raise
            with open(f'{channel_path}/messages.csv', 'a') as csv_file:
                writer = csv.writer(csv_file, delimiter=',', quoting=csv.QUOTE_ALL)
                writer.writerows(messages)
            if attachments:
                with open(f'{channel_path}/uploads.csv', 'a') as csv_file:
                    writer = csv.writer(csv_file, delimiter=',', quoting=csv.QUOTE_ALL)
                    writer.writerows(attachments)

        # Return zip file
        zip_filename = 'export.zip'
        file_list = [os.path.relpath(os.path.join(dp, f), 'export')
                     for dp, dn, fn in os.walk(os.path.expanduser(path)) for f in fn]
        self.make_archive(file_list, zip_filename, path)
        response = HttpResponse(open(zip_filename, 'rb'), content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="{zip_filename}"'
        return response

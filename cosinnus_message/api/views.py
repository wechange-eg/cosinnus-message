import csv
import errno
import os
import shutil
import zipfile

from django.db.models import Q, F
from django.contrib.auth import get_user_model
from django.http.response import HttpResponse
from django.template.defaultfilters import slugify
from rest_framework.views import APIView

from postman.models import Message, STATUS_ACCEPTED


class MessageExportView(APIView):

    def _get_users(self):
        """
        Return users
        :return:
        """
        users = []
        qs = get_user_model().objects.filter(is_active=True)
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
            sender_deleted_at__isnull=True,
            recipient_deleted_at__isnull=True,
            moderation_status=STATUS_ACCEPTED,
            parent__isnull=True,
        )
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

    def _get_messages(self, channel, user_ids):
        """
        Return messages in channel
        :return:
        """
        messages = []
        qs = Message.objects.filter(
            sender__in=user_ids,
            #sender_archived=False,
            #recipient_archived=False,
            sender_deleted_at__isnull=True,
            recipient_deleted_at__isnull=True,
            moderation_status=STATUS_ACCEPTED,
        )
        qs = qs.filter(Q(id=channel[0]) |
                       Q(thread_id=channel[0]))
        qs = qs.order_by('sent_at')
        for message in qs:
            if message.thread_id == message.id and message.subject:
                text = f"*{message.subject}*\n{message.body}"
            else:
                text = message.body
            timestamp = int(message.sent_at.timestamp() * 1000)
            messages.append([message.sender_id, timestamp, text])
        return messages

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
        users = self._get_users()
        with open(f'{path}/users.csv', 'w') as csv_file:
            writer = csv.writer(csv_file, delimiter=',', quoting=csv.QUOTE_ALL)
            writer.writerows(users)
        user_ids = set(u[0] for u in users)

        channels = self._get_channels(user_ids)
        with open(f'{path}/channels.csv', 'w') as csv_file:
            writer = csv.writer(csv_file, delimiter=',', quoting=csv.QUOTE_ALL)
            writer.writerows([channel[1:] for channel in channels])

        for channel in channels:
            messages = self._get_messages(channel, user_ids)

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
            with open(f'{channel_path}/messages.csv', 'w') as csv_file:
                writer = csv.writer(csv_file, delimiter=',', quoting=csv.QUOTE_ALL)
                writer.writerows(messages)

        # Return zip file
        zip_filename = 'export.zip'
        file_list = [os.path.relpath(os.path.join(dp, f), 'export')
                     for dp, dn, fn in os.walk(os.path.expanduser(path)) for f in fn]
        self.make_archive(file_list, zip_filename, path)
        response = HttpResponse(open(zip_filename, 'rb'), content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="{zip_filename}"'
        return response

# -*- coding: utf-8 -*-
from south.utils import datetime_utils as datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):
        # Removing unique constraint on 'Message', fields ['group', 'slug']
        db.delete_unique(u'cosinnus_message_message', ['group_id', 'slug'])

        # Deleting model 'Message'
        db.delete_table(u'cosinnus_message_message')

        # Removing M2M table for field attached_objects on 'Message'
        db.delete_table(db.shorten_name(u'cosinnus_message_message_attached_objects'))

        # Removing M2M table for field recipients on 'Message'
        db.delete_table(db.shorten_name(u'cosinnus_message_message_recipients'))


    def backwards(self, orm):
        # Adding model 'Message'
        db.create_table(u'cosinnus_message_message', (
            ('media_tag', self.gf('django.db.models.fields.related.OneToOneField')(to=orm['cosinnus.TagObject'], unique=True, null=True, on_delete=models.PROTECT, blank=True)),
            ('creator', self.gf('django.db.models.fields.related.ForeignKey')(related_name=u'cosinnus_message_message_set', null=True, on_delete=models.PROTECT, to=orm['auth.User'])),
            ('text', self.gf('django.db.models.fields.TextField')()),
            ('isprivate', self.gf('django.db.models.fields.BooleanField')(default=False)),
            (u'id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('group', self.gf('django.db.models.fields.related.ForeignKey')(related_name=u'cosinnus_message_message_set', on_delete=models.PROTECT, to=orm['cosinnus.CosinnusGroup'])),
            ('created', self.gf('django.db.models.fields.DateTimeField')(default=datetime.datetime.now, auto_now_add=True, blank=True)),
            ('isbroadcast', self.gf('django.db.models.fields.BooleanField')(default=False)),
            ('title', self.gf('django.db.models.fields.CharField')(max_length=255)),
            ('slug', self.gf('django.db.models.fields.SlugField')(max_length=55, blank=True)),
        ))
        db.send_create_signal(u'cosinnus_message', ['Message'])

        # Adding M2M table for field attached_objects on 'Message'
        m2m_table_name = db.shorten_name(u'cosinnus_message_message_attached_objects')
        db.create_table(m2m_table_name, (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('message', models.ForeignKey(orm[u'cosinnus_message.message'], null=False)),
            ('attachedobject', models.ForeignKey(orm[u'cosinnus.attachedobject'], null=False))
        ))
        db.create_unique(m2m_table_name, ['message_id', 'attachedobject_id'])

        # Adding M2M table for field recipients on 'Message'
        m2m_table_name = db.shorten_name(u'cosinnus_message_message_recipients')
        db.create_table(m2m_table_name, (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('message', models.ForeignKey(orm[u'cosinnus_message.message'], null=False)),
            ('user', models.ForeignKey(orm[u'auth.user'], null=False))
        ))
        db.create_unique(m2m_table_name, ['message_id', 'user_id'])

        # Adding unique constraint on 'Message', fields ['group', 'slug']
        db.create_unique(u'cosinnus_message_message', ['group_id', 'slug'])


    models = {
        
    }

    complete_apps = ['cosinnus_message']
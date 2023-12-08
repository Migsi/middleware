import csv
import errno
import json
import middlewared.sqlalchemy as sa
import os
import time
import uuid
import yaml

from .utils import (
    AUDIT_DATASET_PATH,
    AUDIT_LIFETIME,
    AUDIT_DEFAULT_RESERVATION,
    AUDIT_DEFAULT_QUOTA,
    AUDIT_DEFAULT_FILL_CRITICAL,
    AUDIT_DEFAULT_FILL_WARNING,
    AUDIT_REPORTS_DIR,
    AUDITED_SERVICES,
)
from .schema.middleware import AUDIT_EVENT_MIDDLEWARE_JSON_SCHEMAS, AUDIT_EVENT_MIDDLEWARE_PARAM_SET
from .schema.smb import AUDIT_EVENT_SMB_JSON_SCHEMAS, AUDIT_EVENT_SMB_PARAM_SET
from middlewared.client import ejson
from middlewared.plugins.zfs_.utils import TNUserProp
from middlewared.schema import (
    accepts, Bool, Dict, Int, List, Patch, Ref, returns, Str, UUID
)
from middlewared.service import filterable, filterable_returns, job, private, ConfigService
from middlewared.service_exception import CallError, ValidationErrors
from middlewared.utils import filter_list
from middlewared.utils.functools import cache
from middlewared.utils.osc import getmntinfo
from middlewared.validators import Range


ALL_AUDITED = [svc[0] for svc in AUDITED_SERVICES]
QUOTA_WARN = TNUserProp.QUOTA_WARN.value
QUOTA_CRIT = TNUserProp.QUOTA_CRIT.value
_GIB = 1024 ** 3


class AuditModel(sa.Model):
    __tablename__ = 'system_audit'

    id = sa.Column(sa.Integer(), primary_key=True)
    retention = sa.Column(sa.Integer(), default=AUDIT_LIFETIME)
    reservation = sa.Column(sa.Integer(), default=AUDIT_DEFAULT_RESERVATION)
    quota = sa.Column(sa.Integer(), default=AUDIT_DEFAULT_QUOTA)
    quota_fill_warning = sa.Column(sa.Integer(), default=AUDIT_DEFAULT_FILL_WARNING)
    quota_fill_critical = sa.Column(sa.Integer(), default=AUDIT_DEFAULT_FILL_CRITICAL)


class AuditService(ConfigService):
    class Config:
        datastore = 'system.audit'
        cli_namespace = 'system.audit'
        datastore_extend = 'audit.extend'
        role_prefix = 'AUDIT'

    ENTRY = Patch(
        'system_audit_update', 'system_audit_config',
        ('add', Int('available')),
        ('add', Dict(
            'space',
            Int('used'),
            Int('used_by_snapshots'),
            Int('available'),
        )),
        ('add', Bool('remote_logging_enabled')),
        ('add', List('enabled_services'))
    )

    @private
    @cache
    def audit_dataset_name(self):
        audit_dev = os.stat(AUDIT_DATASET_PATH).st_dev
        return getmntinfo(audit_dev)[audit_dev]['mount_source']

    @private
    def get_audit_dataset(self):
        ds_name = self.audit_dataset_name()
        ds = self.middleware.call_sync(
            'zfs.dataset.query',
            [['id', '=', ds_name]],
            {'extra': {'retrieve_children': False}, 'get': True}
        )

        for k, default in TNUserProp.quotas():
            try:
                ds[k] = int(ds[k]["rawvalue"])
            except (KeyError, ValueError):
                ds[k] = default

        return ds

    @private
    def extend(self, data):
        sys_adv = self.middleware.call_sync('system.advanced.config')
        data['remote_logging_enabled'] = bool(sys_adv['syslogserver']) and sys_adv['syslog_audit']
        ds_info = self.get_audit_dataset()
        data['space'] = {'used': None, 'used_by_snapshots': None, 'available': None}
        data['space']['used'] = ds_info['properties']['used']['parsed']
        data['space']['used_by_dataset'] = ds_info['properties']['usedbydataset']['parsed']
        data['space']['used_by_reservation'] = ds_info['properties']['usedbyrefreservation']['parsed']
        data['space']['used_by_snapshots'] = ds_info['properties']['usedbysnapshots']['parsed']
        data['space']['available'] = ds_info['properties']['available']['parsed']
        data['enabled_services'] = {'MIDDLEWARE': [], 'SMB': []}
        audited_smb_shares = self.middleware.call_sync(
            'sharing.smb.query', [['audit.enable', '=', True]], {'select': ['name', 'audit']}
        )

        for share in audited_smb_shares:
            data['enabled_services']['SMB'].append(share['name'])

        return data

    @private
    async def compress(self, data):
        for key in ['space', 'enabled_services', 'remote_logging_enabled']:
            data.pop(key, None)

        return data

    @accepts(Dict(
        'audit_query',
        List('services', items=[Str('db_name', enum=ALL_AUDITED)], default=ALL_AUDITED),
        Ref('query-filters'),
        Ref('query-options'),
        register=True
    ), roles=['AUDIT_READ'])
    @filterable_returns(Dict(
        'audit_entry',
        UUID('audit_id'),
        Int('message_timestamp'),
        Dict('timestamp', additional_attrs=True),
        Str('address'),
        Str('username'),
        UUID('session'),
        Str('service', enum=ALL_AUDITED),
        Dict('service_data', additional_attrs=True, null=True),
        Str('event'),
        Dict('event_data', additional_attrs=True, null=True),
        Bool('success')
    ))
    async def query(self, data):
        """
        Query contents of audit databases specified by `services`.

        If the query-option `force_sql_filters` is true, then the query will be
        converted into a more efficient form for better performance. This will
        not be possible if filters use keys within `svc_data` and `event_data`.

        Each audit entry contains the following keys:

        `audit_id` - GUID uniquely identifying this specific audit event.

        `message_timestamp` - Unix timestamp for when the audit event was
        written to the auditing database.

        `timestamp` - converted ISO-8601 timestamp from application recording
        when event occurred.

        `address` - IP address of client performing action that generated the
        audit message.

        `username` - Username used by client performing action.

        `session` - GUID uniquely identifying the client session.

        `services` - Name of the service that generated the message. This will
        be one of the names specified in `services`.

        `service_data` - JSON object containing variable data depending on the
        particular service. See TrueNAS auditing documentation for the service
        in question.

        `event` - Name of the event type that generated the audit record. Each
        service has its own unique event identifiers.

        `event_data` - JSON object containing variable data depending on the
        particular event type. See TrueNAS auditing documentation for the
        service in question.

        `success` - boolean value indicating whether the action generating the
        event message succeeded.
        """
        results = []
        sql_filters = data['query-options']['force_sql_filters']

        verrors = ValidationErrors()
        if (select := data['query-options'].get('select')):
            for idx, entry in enumerate(select):
                if isinstance(entry, list):
                    entry = entry[0]

                if entry not in (AUDIT_EVENT_MIDDLEWARE_PARAM_SET | AUDIT_EVENT_SMB_PARAM_SET):
                    verrors.add(
                        f'audit.query.query-options.select.{idx}',
                        f'{entry}: column does not exist'
                    )

        verrors.check()

        if sql_filters:
            filters = data['query-filters']
            options = data['query-options']
        else:
            filters = []
            options = {}

        for svc in data['services']:
            entries = await self.middleware.call('auditbackend.query', svc, filters, options)
            results.extend(entries)

        if sql_filters:
            return

        return filter_list(results, data['query-filters'], data['query-options'])

    @accepts(Patch(
        'audit_query', 'audit_export',
        ('add', Str('export_format', enum=['CSV', 'JSON', 'YAML'], default='JSON')),
    ), roles=['AUDIT_READ'])
    @returns(Str('audit_file_path'))
    @job()
    def export(self, job, data):
        """
        Generate an audit report based on the specified `query-filters` and
        `query-options` for the specified `services` in the specified `export_format`.

        Supported export_formats are CSV, JSON, and YAML. The endpoint returns a
        local filesystem path where the resulting audit report is located.
        """
        if data['query-options'].get('count') is True:
            raise CallError('Raw row count may not be exported', errno.EINVAL)

        if data['query-options'].get('get') is True:
            raise CallError(
                'Use of "get" query-option is not supported for export',
                errno.EINVAL
            )

        export_format = data.pop('export_format')
        job.set_progress(0, f'Quering data for {export_format} audit report')
        if not (res := self.middleware.call_sync('audit.query', data)):
            raise CallError('No entries were returned by query.', errno.ENOENT)

        if job.credentials and job.credentials.is_user_session:
            username = job.credentials.user['username']
        else:
            username = 'root'

        target_dir = os.path.join(AUDIT_REPORTS_DIR, username)
        os.makedirs(target_dir, mode=0o700, exist_ok=True)

        filename = f'{uuid.uuid4()}.{export_format.lower()}'
        destination = os.path.join(target_dir, filename)
        with open(destination, 'w') as f:
            job.set_progress(50, f'Writing audit report to {destination}.')
            match export_format:
                case 'CSV':
                    fieldnames = res[0].keys()
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    for entry in res:
                        if entry.get('service_data'):
                            entry['service_data'] = json.dumps(entry['service_data'])
                        if entry.get('event_data'):
                            entry['event_data'] = json.dumps(entry['event_data'])
                        writer.writerow(entry)
                case 'JSON':
                    ejson.dump(res, f, indent=4)
                case 'YAML':
                    yaml.dump(res, f)

        job.set_progress(100, f'Audit report completed and available at {destination}')
        return os.path.join(target_dir, destination)

    @private
    def __process_reports_entry(self, entry, cutoff):
        if not entry.is_file():
            self.logger.warning(
                '%s: unexpected item in audit reports directory',
                entry.name
            )
            return

        if not entry.name.endswith(('.csv', '.json', '.yaml')):
            self.logger.warning(
                '%s: unexpected file type in audit reports directory',
                entry.name
            )
            return

        if entry.stat().st_mtime > cutoff:
            return

        try:
            os.unlink(entry.path)
        except Exception:
            self.logger.error(
                '%s: failed to remove file for audit reports directory.',
                entry.name, exc_info=True
            )

    @private
    def cleanup_reports(self):
        """
        Remove old audit reports. Precision is not of high priority. In most
        circumstances users will download the report within a few minutes.
        """
        retention = self.middleware.call_sync('audit.config')['retention']
        cutoff = int(time.time()) - (retention * 86400)
        try:
            with os.scandir(AUDIT_REPORTS_DIR) as it:
                for entry in it:
                    if not entry.is_dir():
                        continue

                    with os.scandir(entry.path) as subdir:
                        for subentry in subdir:
                            self.__process_reports_entry(subentry, cutoff)
        except FileNotFoundError:
            os.mkdir(AUDIT_REPORTS_DIR, 0o700)

    @private
    async def validate_local_storage(self, new, old, verrors):
        new_volsize = new['quota'] * _GIB
        used = new['space']['used_by_dataset'] + new['space']['used_by_snapshots']
        if old['quota'] != new['quota']:
            if used / new_volsize > new['quota_fill_warning'] / 100:
                verrors.add(
                    'audit_update.quota',
                    'Specified quota would result in the percentage used of the '
                    'audit dataset to exceed the maximum permitted by the configured '
                    'quota_fill_warning.'
                )
        if new['quota'] < new['reservation']:
            verrors.add(
                'audit_update.quota',
                'Quota on auditing dataset must be greater than or equal to '
                'the space reservation for the dataset.'
            )

    @private
    async def update_audit_dataset(self, new):
        ds = await self.middleware.call('audit.get_audit_dataset')
        ds_props = ds['properties']
        old_reservation = ds_props['refreservation']['parsed'] or 0
        old_quota = ds_props['quota']['parsed'] or 0
        old_warn = int(ds_props.get(QUOTA_WARN, {}).get('rawvalue', '0'))
        old_crit = int(ds_props.get(QUOTA_CRIT, {}).get('rawvalue', '0'))

        payload = {}
        if new['quota'] != old_quota / _GIB:
            payload['refquota'] = {'parsed': f'{new["quota"]}G'}

        if new['reservation'] != old_reservation / _GIB:
            payload['refreservation'] = {'parsed': f'{new["reservation"]}G'}

        if new["quota_fill_warning"] != old_warn:
            payload[QUOTA_WARN] = {'parsed': str(new['quota_fill_warning'])}

        if new["quota_fill_critical"] != old_crit:
            payload[QUOTA_CRIT] = {'parsed': str(new['quota_fill_critical'])}

        if not payload:
            return

        await self.middleware.call(
            'zfs.dataset.update', ds['id'], {'properties': payload}
        )

    @accepts(Dict(
        'system_audit_update',
        Int('retention', validators=[Range(1, 30)]),
        Int('reservation', validators=[Range(0, 100)]),
        Int('quota', validators=[Range(0, 100)]),
        Int('quota_fill_warning', validators=[Range(5, 80)]),
        Int('quota_fill_critical', validators=[Range(50, 95)]),
        register=True
    ))
    async def update(self, data):
        """
        Update default audit settings.

        The following fields may be modified:

        `retention` - number of days to retain local audit messages.

        `reservation` - size in GiB of refreservation to set on ZFS dataset
        where the audit databases are stored. The refreservation specifies the
        minimum amount of space guaranteed to the dataset, and counts against
        the space available for other datasets in the zpool where the audit
        dataset is located.

        `quota` - size in GiB of the maximum amount of space that may be
        consumed by the dataset where the audit dabases are stored.

        `quota_fill_warning` - percentage used of dataset quota at which to
        generate a warning alert.

        `quota_fill_critical` - percentage used of dataset quota at which to
        generate a critical alert.

        The following fields contain read-only data and are returned in calls
        to `audit.config` and `audit.update`:

        `space` - ZFS dataset properties relating space used and available for
        the dataset where the audit databases are written.

        `remote_logging_enabled` - Boolean indicating whether logging to a
        remote syslog server is enabled on TrueNAS and if audit logs are
        included in what is sent remotely.

        `enabled_services` - JSON object with key denoting service, and value
        containing a JSON array of what aspects of this service are being
        audited. In the case of the SMB audit, the list contains share names
        of shares for which auditing is enabled.
        """
        old = await self.config()
        new = old.copy()
        new.update(data)

        verrors = ValidationErrors()
        await self.validate_local_storage(new, old, verrors)
        verrors.check()

        await self.update_audit_dataset(new)
        await self.compress(new)
        await self.middleware.call('datastore.update', self._config.datastore, old['id'], new)
        return await self.config()

    @private
    async def setup(self):
        """
        This method should only be called once per upgrade to clean up any stale
        refreservations from old boot environments and to apply the audit dataset
        configuration to the current boot environment.
        """
        try:
            os.mkdir(AUDIT_REPORTS_DIR, 0o700)
        except FileExistsError:
            os.chmod(AUDIT_REPORTS_DIR, 0o700)

        cur = await self.middleware.call('audit.get_audit_dataset')
        parent = os.path.dirname(cur['id'])

        # Explicitly look up pool name. If somehow audit dataset ends up being
        # on a pool that isn't the boot-pool, we don't want to recursively
        # remove refreservations on it.
        boot_pool = await self.middleware.call('boot.pool_name')

        # Get dataset names of any dataset on boot pool that isn't on the current
        # activated boot environment.
        to_remove = await self.middleware.call('zfs.dataset.query', [
            ['id', '!=', cur['id']],
            ['id', '!^', f'{parent}/'],
            ['pool', '=', boot_pool],
            ['properties.refreservation.parsed', '!=', None]
        ], {'select': ['id']})

        if to_remove:
            self.logger.debug(
                'Removing refreservations from the following datasets: %s',
                ', '.join([ds['id'] for ds in to_remove])
            )

        payload = {'refreservation': {'parsed': None}}
        for ds in to_remove:
            try:
                await self.middleware.call(
                    'zfs.dataset.update', ds['id'], {'properties': payload}
                )
            except Exception:
                self.logger.error(
                    '%s: failed to remove refreservation from dataset. Manual '
                    'cleanup may be required', ds['id'], exc_info=True
                )

        audit_config = await self.middleware.call('audit.config')
        try:
            await self.middleware.call('audit.update_audit_dataset', audit_config)
        except Exception:
            self.logger.error('Failed to apply auditing dataset configuration.', exc_info=True)

    @private
    @filterable
    async def json_schemas(self, filters, options):
        return filter_list(AUDIT_EVENT_MIDDLEWARE_JSON_SCHEMAS + AUDIT_EVENT_SMB_JSON_SCHEMAS, filters, options)

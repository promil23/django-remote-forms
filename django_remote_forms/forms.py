from django.utils.datastructures import SortedDict

from django_remote_forms import fields, logger
from django_remote_forms.utils import resolve_promise
from django.utils.safestring import mark_safe


class RemoteForm(object):
    def __init__(self, form, *args, **kwargs):
        self.form = form

        self.all_fields = set(self.form.fields.keys())

        self.excluded_fields = set(kwargs.pop('exclude', []))
        self.included_fields = set(kwargs.pop('include', []))
        self.readonly_fields = set(kwargs.pop('readonly', []))
        self.ordered_fields = kwargs.pop('ordering', [])

        self.fieldsets = kwargs.pop('fieldsets', {})

        # Make sure all passed field lists are valid
        if self.excluded_fields and not (self.all_fields >= self.excluded_fields):
            logger.warning('Excluded fields %s are not present in form fields' % (self.excluded_fields - self.all_fields))
            self.excluded_fields = set()

        if self.included_fields and not (self.all_fields >= self.included_fields):
            logger.warning('Included fields %s are not present in form fields' % (self.included_fields - self.all_fields))
            self.included_fields = set()

        if self.readonly_fields and not (self.all_fields >= self.readonly_fields):
            logger.warning('Readonly fields %s are not present in form fields' % (self.readonly_fields - self.all_fields))
            self.readonly_fields = set()

        if self.ordered_fields and not (self.all_fields >= set(self.ordered_fields)):
            logger.warning('Readonly fields %s are not present in form fields' % (set(self.ordered_fields) - self.all_fields))
            self.ordered_fields = []

        if self.included_fields | self.excluded_fields:
            logger.warning('Included and excluded fields have following fields %s in common' % (set(self.ordered_fields) - self.all_fields))
            self.excluded_fields = set()
            self.included_fields = set()

        # Extend exclude list from include list
        self.excluded_fields |= (self.included_fields - self.all_fields)

        if not self.ordered_fields:
            if hasattr(self.form.fields, 'keyOrder'):
                self.ordered_fields = self.form.fields.keyOrder
            else:
                self.ordered_fields = self.form.fields.keys()

        self.fields = []

        # Construct ordered field list considering exclusions
        for field_name in self.ordered_fields:
            if field_name in self.excluded_fields:
                continue

            self.fields.append(field_name)

        # Validate fieldset
        fieldset_fields = set()
        if self.fieldsets:
            for fieldset_name, fieldsets_data in self.fieldsets:
                if 'fields' in fieldsets_data:
                    fieldset_fields |= set(fieldsets_data['fields'])

        if not (self.all_fields >= fieldset_fields):
            logger.warning('Following fieldset fields are invalid %s' % (fieldset_fields - self.all_fields))
            self.fieldsets = {}

        if not (set(self.fields) >= fieldset_fields):
            logger.warning('Following fieldset fields are excluded %s' % (fieldset_fields - set(self.fields)))
            self.fieldsets = {}

    def as_dict(self):
        """
        Returns a form as a dictionary that looks like the following:

        form = {
            'non_field_errors': [],
            'label_suffix': ':',
            'is_bound': False,
            'prefix': 'text'.
            'fields': {
                'name': {
                    'type': 'type',
                    'errors': {},
                    'help_text': 'text',
                    'label': 'text',
                    'initial': 'data',
                    'max_length': 'number',
                    'min_length: 'number',
                    'required': False,
                    'bound_data': 'data'
                    'widget': {
                        'attr': 'value'
                    }
                }
            }
        }
        """
        form_dict = SortedDict()
        if getattr(self, 'is_empty_form', False):
            form_dict['title'] = self.form.__class__.__name__
            form_dict['non_field_errors'] = self.form.non_field_errors()
            form_dict['label_suffix'] = self.form.label_suffix
            form_dict['is_bound'] = self.form.is_bound
            form_dict['prefix'] = self.form.prefix
            form_dict['errors'] = self.form.errors
            form_dict['fieldsets'] = getattr(self.form, 'fieldsets', [])
            # If there are no fieldsets, specify order
            form_dict['ordered_fields'] = self.fields

        form_dict['fields'] = SortedDict()
        form_dict['inlines'] = SortedDict()


        self.collect_fields(self.form, form_dict)

        #import json
        #print json.dumps(form_dict, indent=4)
        #return mark_safe(json.dumps(form_dict, indent=4))
        return form_dict
        #return resolved
        #return mark_safe(form_dict)

    def collect_fields(self, form, form_dict):
        initial_data = {}

        inlines = getattr(form, 'inlines', None)
        nested = getattr(form, 'nested', None)

        if inlines or nested:
            inl_nes = 'inlines' if inlines else 'nested'
            form_dict[inl_nes] = {}
            for fs_name, fs in getattr(form, inl_nes).items():
                form_dict[inl_nes][fs_name + '-empty'] = \
                                        RemoteForm(fs.empty_form).as_dict()

                for i, f in enumerate(fs.forms):
                    #form_dict[inl_nes].setdefault(fs_name, []).append({})
                    form_dict[inl_nes].setdefault(fs_name, 
                                        {'items':[]})
                    
                    form_dict[inl_nes][fs_name]['items'].append({})
                    self.collect_fields(f, \
                                 form_dict[inl_nes][fs_name]['items'][i])


        for name, value in [(x, form[x].value()) for x in form.fields]:

            form_initial_field_data = form.initial.get(name)
            field = form.fields[name]
            remote_field_class_name = 'Remote%s' % field.__class__.__name__

            field_dict = {}
            try:
                remote_field_class = getattr(fields, remote_field_class_name)
                remote_field = remote_field_class(field, form_initial_field_data, field_name=name)
                if hasattr(remote_field, 'get_dict'):
                    #field_dict = remote_field.as_dict()
                    field_dict = remote_field.get_dict()

                form_dict[name] = {
                    'value': value
                }
                form_dict[name].update(field_dict)
            except Exception, e:
                #logger.warning('Error serializing field %s: %s', remote_field_class_name, str(e))
                print 'Error serializing field {0}: {1}'.format(remote_field_class_name, str(e))




        '''
        for name, field in []:
        #for name, field in [(x, self.form.fields[x]) for x in self.fields]:
            # Retrieve the initial data from the form itself if it exists so
            # that we properly handle which initial data should be returned in
            # the dictionary.

            # Please refer to the Django Form API documentation for details on
            # why this is necessary:
            # https://docs.djangoproject.com/en/dev/ref/forms/api/#dynamic-initial-values
            form_initial_field_data = self.form.initial.get(name)

            # Instantiate the Remote Forms equivalent of the field if possible
            # in order to retrieve the field contents as a dictionary.
            remote_field_class_name = 'Remote%s' % field.__class__.__name__
            try:
                remote_field_class = getattr(fields, remote_field_class_name)
                remote_field = remote_field_class(field, form_initial_field_data, field_name=name)
            except Exception, e:
                logger.warning('Error serializing field %s: %s', remote_field_class_name, str(e))
                field_dict = {}
            else:
                field_dict = remote_field.as_dict()

            if name in self.readonly_fields:
                field_dict['readonly'] = True

            form_dict['fields'][name] = field_dict

            # Load the initial data, which is a conglomerate of form initial and field initial
            if 'initial' not in form_dict['fields'][name]:
                form_dict['fields'][name]['initial'] = None

            initial_data[name] = form_dict['fields'][name]['initial']

        if self.form.data:
            form_dict['data'] = self.form.data
        else:
            form_dict['data'] = initial_data

        #resolved = resolve_promise(form_dict)
        '''

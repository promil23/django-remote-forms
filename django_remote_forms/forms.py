import json
from django.utils.datastructures import SortedDict

from django_remote_forms import fields, logger
from django_remote_forms.utils import resolve_promise
from django.utils.safestring import mark_safe
import portal.utils as bct_utils

class RemoteForm(object):
    def __init__(self, form, *args, **kwargs):
        self.form = form

        self.all_fields = set(self.form.fields.keys())

        self.excluded_fields = set(kwargs.pop('exclude', []))
        self.included_fields = set(kwargs.pop('include', []))
        self.readonly_fields = set(kwargs.pop('readonly', []))
        self.ordered_fields = kwargs.pop('ordering', [])

        self.fieldsets = kwargs.pop('fieldsets', {})
        self.no_refresh = kwargs.pop('no_refresh', False)

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


        mgmt = {
        }
        '''
            'PATTERNS': {
                'mgmt': [],
                'INITIAL_FORMS': self.inlines['PATTERNS'].management_form['INITIAL_FORMS'].value()
            }
        '''

        #self.collect_fields(self.form, form_dict, mgmt, True)
        #self.collect_fields(self.form, form_dict, mgmt, False)
        self.collect_fields(self.form, form_dict, form_dict['inlines'], True)
        self.collect_fields(self.form, form_dict, form_dict['inlines'], False)

        #print json.dumps(form_dict, indent=4)
        #return mark_safe(json.dumps(form_dict, indent=4))

        #empty form doesn't have formsets_to_refresh
        #if hasattr(self.form, 'formsets_to_refresh'):
        #    mgmt = self.form.formsets_to_refresh()
        #    bct_utils.merge_dicts(form_dict['inlines'], mgmt)

        #print json.dumps(form_dict, indent = 2)
        return form_dict

    def collect_mgmt(self, fs_name, fs, mgmt, i = None, f = None):
        #empty form doesn't have management form,
        #form to be deleted doesn't have management form
        if fs_name == 'empty' or (hasattr(f, 'instance') and not f.instance.id):
            return

        '''
        if fs_name == 'PATTERNS':

            mgmt[fs_name].setdefault('mgmt', [])
            mgmt[fs_name].setdefault('INITIAL_FORMS', 
                                     fs.management_form['INITIAL_FORMS'].value()
            )
        else:
        '''
        mgmt.setdefault(fs_name, {
                'mgmt': [],
                'INITIAL_FORMS': fs.management_form['INITIAL_FORMS'].value()

        })
        #just create children INITIAL_FORMS
        if i is None:
            return
        #print mgmt

        #if not f.instance.id:
        #    return

        d = {'id': f.instance.id, 'DELETE': '', 'children': {}}
        mgmt[fs_name]['mgmt'].append(d)

    def collect_fields(self, form, form_dict, mgmt, is_empty):
        initial_data = {}

        inlines = getattr(form, 'inlines', None)
        nested = getattr(form, 'nested', None)

        if inlines or nested:
            inl_nes = 'inlines' if inlines else 'nested'
            form_dict.setdefault(inl_nes, {})
            for fs_name, fs in getattr(form, inl_nes).items():
                if is_empty:
                    form_dict[inl_nes].setdefault(fs_name + '-empty', \
                                            RemoteForm(fs.empty_form).as_dict())
                    self.collect_fields(fs.empty_form, \
                         form_dict[inl_nes][fs_name + '-empty'], 'empty', is_empty)
                else:
                    #if PATTERN does not have any YARNS and TOOLS
                    #we have to set default INITIAL_FORMS values for 
                    #these children
                    self.collect_mgmt(fs_name, fs, mgmt)

                    #second level eg. YARNS, TOOLS
                    form_dict[inl_nes].setdefault(fs_name, {'items': []})
                    #first level eg. PATTERNS
                    form_dict[inl_nes][fs_name].setdefault('items', [])
                    #print fs.total_form_count()
                    #print fs_name
                    #print len(fs.forms)

                    for i, f in enumerate(fs.forms):
                        self.collect_mgmt(fs_name, fs, mgmt, i, f)
                        mgmt[fs_name]['mgmt'][i]['children'] = {}

                        form_dict[inl_nes][fs_name]['items'].append({})
                        self.collect_fields(f, \
                             form_dict[inl_nes][fs_name]['items'][i], 
                             mgmt[fs_name]['mgmt'][i]['children'], is_empty)
                        #self.collect_fields(f, \
                        #     form_dict[inl_nes][fs_name]['items'][i], 
                        #     {}, is_empty)

        for name, value in [(x, form[x].value()) for x in form.fields]:
            form_initial_field_data = form.initial.get(name)
            field = form.fields[name]
            remote_field_class_name = 'Remote%s' % field.__class__.__name__
            #if remote_field_class_name.find('ChoiceField') > -1:
            #    print 'eee   ' + name

            field_dict = {}
            #try:
            remote_field_class = getattr(fields, remote_field_class_name)
            remote_field = remote_field_class(field, form_initial_field_data, field_name=name)
            if hasattr(remote_field, 'get_dict'):
                #field_dict = remote_field.as_dict()
                field_dict = remote_field.get_dict()

            form_dict[name] = {
                'value': value if value is not None else '' 
            }

            #let angular know that we don't want to submit this field
            if getattr(field, 'angular_no_save', False): 
                form_dict[name]['no-save'] = True
            form_dict[name].update(field_dict)
            #except Exception, e:
            #    print 'Error serializing field {0}: {1}'.format(remote_field_class_name, str(e))


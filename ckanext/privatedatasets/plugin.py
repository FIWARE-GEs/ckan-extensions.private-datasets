import ckan.plugins as p
import ckan.plugins.toolkit as tk
import auth
import actions
import constants
import converters_validators as conv_val
import db
import helpers as helpers


class PrivateDatasets(p.SingletonPlugin, tk.DefaultDatasetForm):

    p.implements(p.IDatasetForm)
    p.implements(p.IAuthFunctions)
    p.implements(p.IConfigurer)
    p.implements(p.IRoutes, inherit=True)
    p.implements(p.IActions)
    p.implements(p.IPackageController)
    p.implements(p.ITemplateHelpers)

    ######################################################################
    ############################ DATASET FORM ############################
    ######################################################################

    def _modify_package_schema(self):
        return {
            # remove datasets_with_no_organization_cannot_be_private validator
            'private': [tk.get_validator('ignore_missing'),
                        tk.get_validator('boolean_validator')],
            constants.ALLOWED_USERS_STR: [tk.get_validator('ignore_missing'),
                                          conv_val.allowed_users_convert,
                                          conv_val.private_datasets_metadata_checker],
            constants.ALLOWED_USERS: [tk.get_validator('ignore_missing'),
                                      conv_val.private_datasets_metadata_checker],
            constants.ADQUIRE_URL: [tk.get_validator('ignore_missing'),
                                    conv_val.private_datasets_metadata_checker,
                                    tk.get_converter('convert_to_extras')],
            constants.SEARCHABLE: [tk.get_validator('ignore_missing'),
                                   conv_val.private_datasets_metadata_checker,
                                   tk.get_converter('convert_to_extras'),
                                   tk.get_validator('boolean_validator')]
        }

    def create_package_schema(self):
        # grab the default schema in our plugin
        schema = super(PrivateDatasets, self).create_package_schema()
        schema.update(self._modify_package_schema())
        return schema

    def update_package_schema(self):
        # grab the default schema in our plugin
        schema = super(PrivateDatasets, self).update_package_schema()
        schema.update(self._modify_package_schema())
        return schema

    def show_package_schema(self):
        schema = super(PrivateDatasets, self).show_package_schema()
        schema.update({
            constants.ALLOWED_USERS: [conv_val.get_allowed_users,
                                      tk.get_validator('ignore_missing')],
            constants.ADQUIRE_URL: [tk.get_converter('convert_from_extras'),
                                    tk.get_validator('ignore_missing')],
            constants.SEARCHABLE: [tk.get_converter('convert_from_extras'),
                                   tk.get_validator('ignore_missing')]
        })
        return schema

    def is_fallback(self):
        # Return True to register this plugin as the default handler for
        # package types not handled by any other IDatasetForm plugin.
        return True

    def package_types(self):
        # This plugin doesn't handle any special package types, it just
        # registers itself as the default (above).
        return []

    ######################################################################
    ########################### AUTH FUNCTIONS ###########################
    ######################################################################

    def get_auth_functions(self):
        return {'package_show': auth.package_show,
                'package_update': auth.package_update,
                'resource_show': auth.resource_show,
                constants.PACKAGE_ADQUIRED: auth.package_adquired}

    ######################################################################
    ############################ ICONFIGURER #############################
    ######################################################################

    def update_config(self, config):
        # Add this plugin's templates dir to CKAN's extra_template_paths, so
        # that CKAN will use this plugin's custom templates.
        tk.add_template_directory(config, 'templates')

        # Register this plugin's fanstatic directory with CKAN.
        tk.add_resource('fanstatic', 'privatedatasets')

    ######################################################################
    ############################## IROUTES ###############################
    ######################################################################

    def after_map(self, m):
        # DataSet adquired notification
        m.connect('user_adquired_datasets', '/dashboad/adquired', ckan_icon='shopping-cart',
                  controller='ckanext.privatedatasets.controllers.ui_controller:AdquiredDatasetsControllerUI',
                  action='user_adquired_datasets', conditions=dict(method=['GET']))

        return m

    ######################################################################
    ############################## IACTIONS ##############################
    ######################################################################

    def get_actions(self):
        return {constants.PACKAGE_ADQUIRED: actions.package_adquired}

    ######################################################################
    ######################### IPACKAGECONTROLLER #########################
    ######################################################################

    def before_index(self, pkg_dict):

        if 'extras_' + constants.SEARCHABLE in pkg_dict:
            if pkg_dict['extras_searchable'] == 'False':
                pkg_dict['capacity'] = 'private'
            else:
                pkg_dict['capacity'] = 'public'

        return pkg_dict

    def before_view(self, pkg_dict):
        return pkg_dict

    def before_search(self, search_params):
        return search_params

    def create(self, pkg_dict):
        return pkg_dict

    def edit(self, pkg_dict):
        return pkg_dict

    def read(self, pkg_dict):
        return pkg_dict

    def delete(self, pkg_dict):
        return pkg_dict

    def after_create(self, context, pkg_dict):
        session = context['session']

        db.init_db(context['model'])

        # Get the users and the package ID
        if constants.ALLOWED_USERS in pkg_dict:

            # When the user removes all the users using the UI, we recieve an array with one
            # element that is an empty string, so set the value properly
            if len(pkg_dict[constants.ALLOWED_USERS]) == 1 and pkg_dict[constants.ALLOWED_USERS][0] == '':
                pkg_dict[constants.ALLOWED_USERS] = []

            allowed_users = pkg_dict[constants.ALLOWED_USERS]
            package_id = pkg_dict['id']

            # Get current users
            users = db.AllowedUser.get(package_id=package_id)

            # Delete users and save the list of current users
            current_users = []
            for user in users:
                current_users.append(user.user_name)
                if user.user_name not in allowed_users:
                    session.delete(user)

            # Add non existing users
            for user_name in allowed_users:
                if user_name not in current_users:
                    out = db.AllowedUser()
                    out.package_id = package_id
                    out.user_name = user_name
                    out.save()
                    session.add(out)

        return pkg_dict

    def after_update(self, context, pkg_dict):
        return self.after_create(context, pkg_dict)

    def after_show(self, context, pkg_dict):

        user_obj = context.get('auth_user_obj')
        updating_via_api = context.get(constants.CONTEXT_CALLBACK, False)

        # Only the package creator can update it
        if not updating_via_api and (not user_obj or (pkg_dict['creator_user_id'] != user_obj.id and not user_obj.sysadmin)):
            attrs = [constants.ALLOWED_USERS, constants.SEARCHABLE, constants.ADQUIRE_URL]
            for attr in attrs:
                if attr in pkg_dict:
                    del pkg_dict[attr]

        return pkg_dict

    def after_search(self, search_results, search_params):
        return search_results

    def after_delete(self, context, pkg_dict):
        return pkg_dict

    ######################################################################
    ######################### ITEMPLATESHELPER ###########################
    ######################################################################

    def get_helpers(self):
        return {'privatedatasets_adquired': helpers.is_adquired,
                'get_allowed_users_str': helpers.get_allowed_users_str,
                'is_owner': helpers.is_owner}

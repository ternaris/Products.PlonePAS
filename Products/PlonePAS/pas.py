##############################################################################
#
# PlonePAS - Adapt PluggableAuthService for use in Plone
# Copyright (C) 2005 Enfold Systems, Kapil Thangavelu, et al
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this
# distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
#
##############################################################################
"""
pas alterations and monkies
$Id$
"""
import sys
from sets import Set

from Acquisition import aq_inner, aq_parent
from AccessControl.PermissionRole import _what_not_even_god_should_do
from AccessControl.Permissions import manage_users as ManageUsers

from Products.CMFCore.utils import getToolByName

from Products.PluggableAuthService.PropertiedUser import PropertiedUser
from Products.PluggableAuthService.PluggableAuthService import \
     PluggableAuthService, _SWALLOWABLE_PLUGIN_EXCEPTIONS, LOG, BLATHER
from Products.PluggableAuthService.PluggableAuthService import security
from Products.PluggableAuthService.interfaces.plugins import IRoleAssignerPlugin
from Products.PluggableAuthService.interfaces.plugins import IUserEnumerationPlugin
from Products.PluggableAuthService.interfaces.plugins import IGroupEnumerationPlugin

from Products.PlonePAS.interfaces.plugins import IUserManagement, ILocalRolesPlugin
from Products.PlonePAS.interfaces.group import IGroupIntrospection
from Products.PlonePAS.interfaces.plugins import IUserIntrospection

#################################
# pas folder monkies - standard zope user folder api

_old_doAddUser = PluggableAuthService._doAddUser
def _doAddUser(self, login, password, roles, domains, groups=None, **kw ):
    """Masking of PAS._doAddUser to add groups param."""
    retval = _old_doAddUser(self, login, password, roles, domains)
    if groups is not None:
        self.userSetGroups(login, groups)
    return retval

PluggableAuthService._doAddUser = _doAddUser

def _doDelUsers(self, names):
    """
    Delete users given by a list of user ids.
    Has no return value, like the original.
    """
    for name in names:
        self._doDelUser(name)

PluggableAuthService._doDelUsers = _doDelUsers

 
def _doDelUser(self, id):
    """
    Given a user id, hand off to a deleter plugin if available.
    """
    plugins = self._getOb('plugins')
    userdeleters = plugins.listPlugins(IUserManagement)

    if not userdeleters:
        raise NotImplementedError("There is no plugin that can "
                                   " delete users.")

    for userdeleter_id, userdeleter in userdeleters:
        userdeleter.doDeleteUser(id)
PluggableAuthService._doDelUser = _doDelUser

security.declareProtected(ManageUsers, 'userFolderDelUsers')
PluggableAuthService.userFolderDelUsers = PluggableAuthService._doDelUsers


def _doChangeUser(self, principal_id, password, roles, domains=(), groups=None, **kw):
    """
    Given a principal id, change its password, roles, domains, iff
    respective plugins for such exist.

    XXX domains are currently ignored.
    """
    # Might be called with 'None' as password from the Plone UI, in
    # prefs_users_overview when resetPassword is not set.
    if password is not None:
        self.userSetPassword(principal_id, password)

    plugins = self._getOb('plugins')
    rmanagers = plugins.listPlugins(IRoleAssignerPlugin)

    if not (rmanagers):
        raise NotImplementedError("There is no plugin that can modify roles")

    for rid, rmanager in rmanagers:
        rmanager.assignRolesToPrincipal(roles, principal_id)

    if groups is not None:
        self.userSetGroups(principal_id, groups)

    return True

PluggableAuthService._doChangeUser = _doChangeUser

security.declareProtected(ManageUsers, 'userFolderEditUser')
PluggableAuthService.userFolderEditUser = PluggableAuthService._doChangeUser


# ttw alias
# XXX need to security restrict these methods, no base class sec decl
#PluggableAuthService.userFolderAddUser__roles__ = ()
def userFolderAddUser(self, login, password, roles, domains, groups=None, **kw ):
    self._doAddUser(login, password, roles, domains, **kw)
    if groups is not None:
        self.userSetGroups(login, groups)

PluggableAuthService.userFolderAddUser = userFolderAddUser


def _doAddGroup(self, id, roles, groups=None, **kw):
    gtool = getToolByName(self, 'portal_groups')
    return gtool.addGroup(id, roles, groups, **kw)

PluggableAuthService._doAddGroup = _doAddGroup

# for prefs_group_manage compatibility. really should be using tool.
def _doDelGroups(self, names):
    gtool = getToolByName(self, 'portal_groups')
    for group_id in names:
        gtool.removeGroup(group_id)

PluggableAuthService._doDelGroups = _doDelGroups

security.declareProtected(ManageUsers, 'userFolderDelGroups')
PluggableAuthService.userFolderDelGroups = PluggableAuthService._doDelGroups


def _doChangeGroup(self, principal_id, roles, groups=None, **kw):
    """
    Given a group's id, change its roles, domains, iff respective
    plugins for such exist.

    XXX domains are currently ignored.

    See also _doChangeUser
    """
    gtool = getToolByName(self, 'portal_groups')
    gtool.editGroup(principal_id, roles, groups, **kw)
    return True
PluggableAuthService._doChangeGroup = _doChangeGroup

def _updateGroup(self, principal_id, roles=None, groups=None, **kw):
    """
    Given a group's id, change its roles, groups, iff respective
    plugins for such exist.

    XXX domains are currently ignored.

    This is not an alias to _doChangeGroup because its params are different (slightly).
    """
    return self._doChangeGroup(principal_id, roles, groups, **kw)
PluggableAuthService._updateGroup = _updateGroup

security.declareProtected(ManageUsers, 'userFolderEditGroup')
PluggableAuthService.userFolderEditGroup = PluggableAuthService._doChangeGroup


security.declareProtected(ManageUsers, 'getGroups')
def getGroups(self):
    gtool = getToolByName(self, 'portal_groups')
    return gtool.listGroups()
PluggableAuthService.getGroups = getGroups

security.declareProtected(ManageUsers, 'getGroupNames')
def getGroupNames(self):
    gtool = getToolByName(self, 'portal_groups')
    return gtool.getGroupIds()
PluggableAuthService.getGroupNames = getGroupNames

security.declareProtected(ManageUsers, 'getGroupIds')
def getGroupIds(self):
    gtool = getToolByName(self, 'portal_groups')
    return gtool.getGroupIds()
PluggableAuthService.getGroupIds = getGroupIds

security.declareProtected(ManageUsers, 'getGroup')
def getGroup(self, group_id):
    """Like getGroupById in groups tool, but doesn't wrap.
    """
    group = None
    introspectors = self.plugins.listPlugins(IGroupIntrospection)

    if not introspectors:
        raise NotSupported, 'No plugins allow for group management'
    for iid, introspector in introspectors:
        group = introspector.getGroupById(group_id)
        if group is not None:
            break
    return group
PluggableAuthService.getGroup = getGroup


security.declareProtected(ManageUsers, 'getGroupByName')
def getGroupByName(self, name, default = None):
    ret = self.getGroup(name)
    if ret is None:
        return default
    return ret
PluggableAuthService.getGroupByName = getGroupByName


security.declareProtected(ManageUsers, 'getGroupById')
def getGroupById(self, id, default = None):
    gtool = getToolByName(self, "portal_groups")
    ret = gtool.getGroupById(id)
    if ret is None:
        return default
    else:
        return ret
	    
PluggableAuthService.getGroupById = getGroupById


security.declarePublic("getLocalRolesForDisplay")
def getLocalRolesForDisplay(self, object):
    """This is used for plone's local roles display

    This method returns a tuple (massagedUsername, roles, userType,
    actualUserName).  This method is protected by the 'access content
    information' permission. We may change that if it's too
    permissive...

    A GRUF method originally.
    """
    result = []
    # we don't have a PAS-side way to get this
    local_roles = object.get_local_roles()
    for one_user in local_roles:
        username = one_user[0]
        roles = one_user[1]
        userType = 'user'
        if self.getGroup(username):
            userType = 'group'
        result.append((username, roles, userType, username))
    return tuple(result)
PluggableAuthService.getLocalRolesForDisplay = getLocalRolesForDisplay


def getUsers(self):
    """
    Return a list of all users from plugins that implement the user
    introspection interface.

    Could potentially be very long.
    """
    # We should have a method that's cheap about returning number of users.
    retval = []
    plugins = self._getOb('plugins')
    introspectors = self.plugins.listPlugins(IUserIntrospection)

    for iid, introspector in introspectors:
        retval += introspector.getUsers()

    return retval
PluggableAuthService.getUsers = getUsers
PluggableAuthService.getPureUsers = getUsers   # this'll make listMembers work


def canListAllUsers(self):
    plugins = self._getOb('plugins')

    # Do we have multiple user plugins?
    if len(plugins.listPlugins(IUserEnumerationPlugin)) != len(plugins.listPlugins(IUserIntrospection)):
        return False

    # Does our single user enumerator support the needed API?
    #for method in [#'countAllUsers',
    #               'getUsers',
    #               'getUserNames']:
    #    if not hasattr(pas, method):
    #        return False

    return True
PluggableAuthService.canListAllUsers = canListAllUsers


def canListAllGroups(self):
    plugins = self._getOb('plugins')

    # Do we have multiple user plugins?
    if len(plugins.listPlugins(IGroupEnumerationPlugin)) != len(plugins.listPlugins(IGroupIntrospection)):
        return False
    return True
PluggableAuthService.canListAllGroups = canListAllGroups


def userSetPassword(self, userid, password):
    """Emulate GRUF 3 call for password set, for use with PwRT."""
    # used by _doChangeUser
    plugins = self._getOb('plugins')
    managers = plugins.listPlugins(IUserManagement)

    if not (managers):
        raise NotImplementedError("There is no plugin that can modify users")

    modified = False
    for mid, manager in managers:
        try:
            manager.doChangeUser(userid, password)            
        except RuntimeError:
            # XXX: why silent ignore this Error?
            pass
        else:
            modified = True

    if not modified:
        raise RuntimeError ("No user management plugins were able "
                            "to successfully modify the user")
PluggableAuthService.userSetPassword = userSetPassword


def credentialsChanged(self, user, name, new_password):
    """Notifies the authentication mechanism that this user has changed
    passwords.  This can be used to update the authentication cookie.
    Note that this call should *not* cause any change at all to user
    databases.

    For use by CMFCore.MembershipTool.credentialsChanged
    """
    request = self.REQUEST
    response = request.RESPONSE
    login = name

    self.updateCredentials(request, response, login, new_password)
PluggableAuthService.credentialsChanged = credentialsChanged


# for ZopeVersionControl, we need to check 'plugins' for more than
# existence, since it replaces objects (like 'plugins') with SimpleItems
# and calls _delOb, which tries to use special methods of 'plugins'
from OFS.Folder import Folder
def _delOb( self, id ):
    #
    #   Override ObjectManager's version to clean up any plugin
    #   registrations for the deleted object
    #
    # XXX imo this is a evil one
    #
    plugins = self._getOb( 'plugins', None )

    if getattr(plugins, 'removePluginById', None) is not None:
        plugins.removePluginById( id )

    Folder._delOb( self, id )
PluggableAuthService._delOb = _delOb

def addRole( self, role ):
    plugins = self._getOb('plugins')
    roles = plugins.listPlugins(IRoleAssignerPlugin)

    for plugin_id, plugin in roles:
        try:
            plugin.addRole( role )
            return
        except _SWALLOWABLE_PLUGIN_EXCEPTIONS:
            pass
PluggableAuthService.addRole = addRole

def getAllLocalRoles( self, context ):
    plugins = self._getOb('plugins')
    lrmanagers = plugins.listPlugins(ILocalRolesPlugin)

    roles={}
    for lrid, lrmanager in lrmanagers:
        newroles=lrmanager.getAllLocalRolesInContext(context)
        for k,v in newroles.items():
            if k not in roles:
                roles[k]=Set()
            roles[k].update(v)

    return roles
PluggableAuthService.getAllLocalRoles = getAllLocalRoles
# Old name, used by CMFPlone.CatalogTool
PluggableAuthService._getAllLocalRoles = getAllLocalRoles


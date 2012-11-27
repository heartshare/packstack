"""
Installs and configures puppet
"""
import logging
import os
import uuid

import packstack.installer.engine_validators as validate
from packstack.installer import basedefs
import packstack.installer.common_utils as utils

from packstack.modules.ospluginutils import gethostlist

# Controller object will be initialized from main flow
controller = None

# Plugin name
PLUGIN_NAME = "OSPUPPET"
PLUGIN_NAME_COLORED = utils.getColoredText(PLUGIN_NAME, basedefs.BLUE)

logging.debug("plugin %s loaded", __name__)

PUPPETDIR      = os.path.abspath(os.path.join(basedefs.DIR_PROJECT_DIR, 'puppet'))
MODULEDIR = os.path.join(PUPPETDIR, "modules")
MANIFESTDIR = os.path.join(PUPPETDIR, "manifests")
PUPPET_MODULES = [
    ('https://github.com/puppetlabs/puppetlabs-glance.git', 'glance', 'folsom'),
    ('https://github.com/puppetlabs/puppetlabs-horizon.git', 'horizon', 'folsom'),
    ('https://github.com/puppetlabs/puppetlabs-keystone.git', 'keystone', 'folsom'),
    ('https://github.com/puppetlabs/puppetlabs-nova.git', 'nova', 'folsom'),
    ('https://github.com/puppetlabs/puppetlabs-openstack.git', 'openstack', 'folsom'),
    ('https://github.com/puppetlabs/puppetlabs-swift.git', 'swift', None),
    ("https://github.com/puppetlabs/puppetlabs-cinder.git", "cinder", "folsom"),
    ('https://github.com/puppetlabs/puppetlabs-stdlib.git', 'stdlib', None),
    ('https://github.com/puppetlabs/puppetlabs-sysctl.git', 'sysctl', None),
    ('https://github.com/puppetlabs/puppetlabs-mysql.git', 'mysql', None),
    ('https://github.com/puppetlabs/puppetlabs-concat.git', 'concat', None),
    ('https://github.com/puppetlabs/puppetlabs-create_resources.git', 'create_resources', None),
    ('https://github.com/puppetlabs/puppetlabs-rsync.git', 'rsync', None),
    ('https://github.com/puppetlabs/puppetlabs-xinetd.git', 'xinetd', None),
    ('https://github.com/puppetlabs/puppetlabs-apache.git', 'apache', None),
    ('https://github.com/lstanden/puppetlabs-firewall.git', 'firewall', None),
    ('https://github.com/saz/puppet-memcached.git', 'memcached', None),
    ('https://github.com/saz/puppet-ssh.git', 'ssh', None),
    ('https://github.com/cprice-puppet/puppetlabs-inifile.git', 'inifile', None),
    ('https://github.com/derekhiggins/puppet-qpid.git', 'qpid', None),
    ('https://github.com/derekhiggins/puppet-vlan.git', 'vlan', None)
]

def initConfig(controllerObject):
    global controller
    controller = controllerObject
    logging.debug("Adding Openstack Puppet configuration")
    paramsList = [
                  {"CMD_OPTION"      : "remove-puppetmodules",
                   "USAGE"           : "Causes the Puppet modules to be removed (if present), and recloned from git (NOTE : may clone a untested version)",
                   "PROMPT"          : "Causes the Puppet modules to be removed (if present), and recloned from git (NOTE : may clone a untested version)",
                   "OPTION_LIST"     : ["y", "n"],
                   "VALIDATION_FUNC" : validate.validateOptions,
                   "DEFAULT_VALUE"   : "n",
                   "MASK_INPUT"      : False,
                   "LOOSE_VALIDATION": True,
                   "CONF_NAME"       : "CONFIG_PUPPET_REMOVEMODULES",
                   "USE_DEFAULT"     : False,
                   "NEED_CONFIRM"    : False,
                   "CONDITION"       : False },
                 ]

    groupDict = { "GROUP_NAME"            : "PUPPET",
                  "DESCRIPTION"           : "Puppet Config paramaters",
                  "PRE_CONDITION"         : utils.returnYes,
                  "PRE_CONDITION_MATCH"   : "yes",
                  "POST_CONDITION"        : False,
                  "POST_CONDITION_MATCH"  : True}

    controller.addGroup(groupDict, paramsList)


def initSequences(controller):
    puppetpresteps = [
             {'title': 'Clean Up', 'functions':[runCleanup]},
    ]
    controller.insertSequence("Clean Up", [], [], puppetpresteps, index=0)

    puppetsteps = [
             {'title': 'Getting Puppet modules', 'functions':[getPuppetModules]},
             {'title': 'Installing Puppet', 'functions':[installpuppet]},
             {'title': 'Copying Puppet modules/manifests', 'functions':[copyPuppetModules]},
             {'title': 'Applying Puppet manifests', 'functions':[applyPuppetManifest]},
    ]
    controller.addSequence("Puppet", [], [], puppetsteps)

    controller.CONF.setdefault('CONFIG_MANIFESTFILES', [])

def runCleanup():
    localserver = utils.ScriptRunner()
    localserver.append("rm -rf %s/*pp"%MANIFESTDIR)
    if controller.CONF["CONFIG_PUPPET_REMOVEMODULES"] == 'y':
        localserver.append("rm -rf %s"%MODULEDIR)
    localserver.execute()

def getPuppetModules():
    localserver = utils.ScriptRunner()
    
    localserver.append('mkdir -p %s'%MODULEDIR)
    for repository, directory, branch in PUPPET_MODULES:
        directory = os.path.join(MODULEDIR, directory)
        localserver.append('[ -d %s ] || git clone %s %s'%(directory, repository, directory))
        if branch:
            localserver.append('[ -d %s/.git ] && cd %s &&  git checkout %s ; cd %s'%(directory, directory, branch, MODULEDIR))

    localserver.execute()

def installpuppet():
    for hostname in gethostlist(controller.CONF):
        server = utils.ScriptRunner(hostname)
        server.append("rpm -q puppet || yum install -y puppet")
        # disable epel if on rhel
        if controller.CONF["CONFIG_USE_EPEL"] == 'n':
            server.append("grep 'Red Hat Enterprise Linux' /etc/redhat-release && sed -i -e 's/enabled=1/enabled=0/g' /etc/yum.repos.d/epel.repo || echo -n ''")
        server.execute()

def copyPuppetModules():
    server = utils.ScriptRunner()
    for hostname in gethostlist(controller.CONF):
        server.append("cd %s"%basedefs.DIR_PROJECT_DIR,)
        server.append("tar --dereference -czf - puppet/manifests puppet/modules | ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@%s tar -C /etc -xzf -"%(hostname))
    server.execute()

def applyPuppetManifest():
    print
    for manifest in controller.CONF['CONFIG_MANIFESTFILES']:
        for hostname in gethostlist(controller.CONF):
            if "/%s_"%hostname not in manifest: continue

            print "Applying "+ manifest
            server = utils.ScriptRunner(hostname)
            server.append("puppet apply /etc/puppet/manifests/%s"%os.path.split(manifest)[1])
            server.execute()

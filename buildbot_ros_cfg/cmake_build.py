from buildbot.config import BuilderConfig
from buildbot.process.factory import BuildFactory
from buildbot.process.properties import Interpolate
from buildbot.steps.source.git import Git
from buildbot.steps.shell import ShellCommand, SetPropertyFromCommand
from buildbot.steps.transfer import FileUpload, FileDownload
from buildbot.steps.trigger import Trigger
from buildbot.steps.master import MasterShellCommand
from buildbot.steps.slave import RemoveDirectory, MakeDirectory
from buildbot.schedulers import triggerable
from buildbot.plugins import steps

from helpers import success
import subprocess
import yaml
import os

## @brief Debbuilds are used for building sourcedebs & binaries out of gbps and uploading to an APT repository
## @param c The Buildmasterconfig
## @param job_name Name for this job (typically the metapackage name)
## @param url URL of the BLOOM repository.
## @param branch The branch that we want to build (for instance, 'master' or 'melodic-devel')
## @param distro Ubuntu distro to build for (for instance, 'precise')
## @param arch Architecture to build for (for instance, 'amd64')
## @param machines List of machines this can build on.
def cmake_branch_build(c, job_name, url, branch, distro, arch, machines):

    f = BuildFactory()

    # Remove the build directory.
    f.addStep(
        RemoveDirectory(
            name = job_name+'-clean',
            dir = Interpolate('%(prop:workdir)s'),
            hideStepIf = success,
        )
    )
    # Pulling the repo
    f.addStep(
        Git(
            repourl = url,
            branch = 'HEAD',
            alwaysUseLatest = True, # this avoids broken builds when schedulers send wrong tag/rev
            mode = 'full', # clean out old versions
            getDescription={'tags': True}
        )
    )
    # Check out the repository branch/commit/tag
    f.addStep(
        ShellCommand(
            haltOnFailure = True,
            name = 'checkout: ' + branch,
            command = ['git', 'checkout', branch],
        )
    )

    f.addStep(
        ShellCommand(
            haltOnFailure = True,
            name = 'cmake',
            command = [
                'cmake',
                '-GNinja',
                '.',
                '-DCMAKE_BUILD_TYPE=Release',
                '-DCMAKE_INSTALL_PREFIX=/opt/'+job_name]
        )
    )

    f.addStep(
        ShellCommand(
            haltOnFailure = True,
            name = 'ninja',
            command = ['ninja']
        )
    )

    f.addStep(
        ShellCommand(
            haltOnFailure = True,
            name = 'cpack',
            command = ['cpack']
        )
    )

    # Add to builders
    c['builders'].append(
        BuilderConfig(
            name = job_name+'_'+'_'+distro+'_'+arch+'_debbuild',
            slavenames = machines,
            factory = f
        )
    )
    # return name of builder created
    return job_name+'_'+'_'+distro+'_'+arch+'_debbuild'

from buildbot.config import BuilderConfig
from buildbot.process.factory import BuildFactory
from buildbot.process.properties import Interpolate
from buildbot.steps.source.git import Git
from buildbot.steps.shell import ShellCommand, SetPropertyFromCommand
from buildbot.steps.transfer import FileUpload, FileDownload
from buildbot.steps.trigger import Trigger
from buildbot.steps.master import MasterShellCommand
from buildbot.steps.slave import RemoveDirectory
from buildbot.schedulers import triggerable

from helpers import success
import subprocess
import yaml
import os

## @brief Debbuilds are used for building sourcedebs & binaries out of gbps and uploading to an APT repository
## @param c The Buildmasterconfig
## @param job_name Name for this job (typically the metapackage name)
## @param packages List of packages to build.
## @param url URL of the BLOOM repository.
## @param branch The branch that we want to build (for instance, 'master' or 'melodic-devel')
## @param distro Ubuntu distro to build for (for instance, 'precise')
## @param arch Architecture to build for (for instance, 'amd64')
## @param rosdistro ROS distro (for instance, 'groovy')
## @param machines List of machines this can build on.
## @param othermirror Cowbuilder othermirror parameter
## @param keys List of keys that cowbuilder will need
## @param trigger_pkgs List of packages names to trigger after our build is done.
def ros_branch_build(c, job_name, packages, url, branch, distro, arch, rosdistro, machines, othermirror, keys, trigger_pkgs = None):
    gbp_args = ['-uc', '-us', '--git-ignore-branch', '--git-ignore-new',
                '--git-verbose', '--git-dist='+distro, '--git-arch='+arch]

    with open(os.path.dirname(os.path.realpath(__file__)) + "/spec.yaml") as file:
        spec_list = yaml.full_load(file)

    f = BuildFactory()

    # Remove the build directory.
    f.addStep(
        RemoveDirectory(
            name = job_name+'-clean',
            dir = Interpolate('%(prop:workdir)s'),
            hideStepIf = success,
        )
    )
    # Check out the repository master branch, since releases are tagged and not branched
    f.addStep(
        Git(
            repourl = url,
            branch = branch,
            alwaysUseLatest = True, # this avoids broken builds when schedulers send wrong tag/rev
            mode = 'full', # clean out old versions
            getDescription={'tags': True}
        )
    )
    # get the short commit hash
    f.addStep(
        SetPropertyFromCommand(
            command="git rev-parse --short HEAD", property="commit_hash",
            name = package+'-commit-short-hash',
            hideStepIf = success
        )
    )
    # Update the cowbuilder
    f.addStep(
        ShellCommand(
            command = ['cowbuilder-update.py', distro, arch] + keys,
            hideStepIf = success
        )
    )
    # Generate the changelog for the package
    f.addStep(
        ShellCommand(
            haltOnFailure = True,
            name = 'catkin_generate_changelog',
            command= ['catkin_generate_changelog', '-y'],
            descriptionDone = ['catkin_generate_changelog']
        )
    )
    # Add all files including untracked ones
    f.addStep(
        ShellCommand(
            haltOnFailure = True,
            name = 'add_changelogs',
            command= ['git', 'add', '.'],
            descriptionDone = ['add_changelogs']
        )
    )
    # Commit the changelog after updating it
    f.addStep(
        ShellCommand(
            haltOnFailure = True,
            name = 'update_changelogs',
            command= ['git', 'commit', '-m', '\"Updated changelogs\"'],
            descriptionDone = ['update_changelogs']
        )
    )
    # Prepare the release without pushing it
    # Set very big number to avoid conflicts with available tags
    f.addStep(
        ShellCommand(
            haltOnFailure = True,
            name = 'catkin_prepare_release',
            command= ['catkin_prepare_release', '--version', '100.0.0', '--no-push', '-y'],
            descriptionDone = ['catkin_prepare_release']
        )
    )
    #
    f.addStep(
        ShellCommand(
            haltOnFailure = True,
            name = 'git_bloom_generate_release',
            command = ['git-bloom-generate', '-y', 'rosrelease', rosdistro],
        )
    )
    f.addStep(
        ShellCommand(
            haltOnFailure = True,
            name = 'git_bloom_generate_debian',
            command = ['git-bloom-generate', '-y', 'rosdebian', '-a', '-p', 'release', rosdistro],
        )
    )
    # Get the tag number for the lastest commit
    f.addStep(
        SetPropertyFromCommand(
            command="git describe --tags", property="release_version",
            name = 'latest_tag',
        )
    )
    # Need to build each package in order
    for package in packages:
        debian_pkg = 'ros-'+rosdistro+'-'+package.replace('_','-')  # debian package name (ros-groovy-foo)
        branch_name = 'debian/'+debian_pkg+'_%(prop:release_version)s-0_'+distro
        deb_name = debian_pkg+'_%(prop:release_version)s-0'+distro
        final_name = debian_pkg+'_%(prop:release_version)s-0'+distro+'_'+arch+'.deb'
        final_name_master = debian_pkg+'_%(prop:release_version)s-%(prop:commit_hash)s'+distro+'_'+arch+'.deb'
        # Check out the proper tag. Use --force to delete changes from previous deb stamping
        f.addStep(
            ShellCommand(
                haltOnFailure = True,
                name = package+'-checkout',
                command = ['git', 'checkout', Interpolate(branch_name), '--force'],
                hideStepIf = success
            )
        )
        # download hooks
        f.addStep(
            FileDownload(
                name = package+'-grab-hooks',
                mastersrc = 'hooks/D05deps',
                slavedest = Interpolate('%(prop:workdir)s/hooks/D05deps'),
                hideStepIf = success,
                mode = 0777 # make this executable for the cowbuilder
            )
        )
        # Download script for building the binary deb
        f.addStep(
            FileDownload(
                name = job_name+'-grab-build-binary-deb-script',
                mastersrc = 'scripts/build_binary_deb.py',
                slavedest = Interpolate('%(prop:workdir)s/build_binary_deb.py'),
                mode = 0755,
                hideStepIf = success
            )
        )
        # build the binary from the git working copy
        f.addStep(
            ShellCommand(
                haltOnFailure = True,
                name = package+'-buildbinary',
                command = [Interpolate('%(prop:workdir)s/build_binary_deb.py'), debian_pkg,
                    Interpolate('%(prop:release_version)s'), distro, Interpolate('%(prop:workdir)s')] + gbp_args,
                env = {'DIST': distro,
                       'GIT_PBUILDER_OPTIONS': Interpolate('--basepath /var/cache/pbuilder/base-{distro}-{arch}.cow '.format(distro=distro, arch=arch)
                                                         + '--hookdir %(prop:workdir)s/hooks --override-config')},
                descriptionDone = ['binarydeb', package]
            )
        )
        # Upload binarydeb to master
        f.addStep(
            FileUpload(
                name = package+'-uploadbinary',
                slavesrc = Interpolate('%(prop:workdir)s/'+final_name),
                masterdest = Interpolate('binarydebs/'+final_name_master),
                hideStepIf = success
            )
        )
        # Add the binarydeb using reprepro updater script on master
        f.addStep(
            MasterShellCommand(
                name = package+'-includedeb',
                command = ['reprepro-include.bash', debian_pkg, Interpolate(final_name_master), distro, arch],
                descriptionDone = ['updated in apt', package]
            )
        )
        f.addStep(
            ShellCommand(
                name = package+'-clean',
                command = ['rm', '-rf', 'debian/'+debian_pkg],
                hideStepIf = success
            )
        )
        if spec_list["sync_s3"]:
            f.addStep(
                ShellCommand(
                    name = package+'-s3-syncing',
                    command = ['s3cmd',
                               '--acl-public',
                               '--delete-removed',
                               '--verbose',
                               'sync',
                               spec_list["local_repo_path"],
                               's3://{s3_bucket}'.format(s3_bucket=spec_list["s3_bucket"])]
                )
            )
    # Create trigger
    c['schedulers'].append(
        triggerable.Triggerable(
            name = job_name.replace('_','-')+'-'+rosdistro+'-'+distro+'-'+arch+'-debtrigger',
            builderNames = [job_name+'_'+rosdistro+'_'+distro+'_'+arch+'_debbuild',]
        )
    )
    # Add to builders
    c['builders'].append(
        BuilderConfig(
            name = job_name+'_'+rosdistro+'_'+distro+'_'+arch+'_debbuild',
            slavenames = machines,
            factory = f
        )
    )
    # return name of builder created
    return job_name+'_'+rosdistro+'_'+distro+'_'+arch+'_debbuild'

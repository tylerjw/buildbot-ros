from buildbot.config import BuilderConfig
from buildbot.process.factory import BuildFactory
from buildbot.steps.trigger import Trigger
from rosdistro import get_source_build_files
from buildbot_ros_cfg.distro import RosDistroOracle

## @brief Create build triggeres
## @param c The Buildmasterconfig
## @param oracle The rosdistro oracle
## @param distro The distro to configure for ('groovy', 'hydro', etc)
## @param builders list of builders that this job can run on
## @returns A list of build it created
def make_build_triggerer(c, oracle, distro, builders):
    build_files = get_source_build_files(oracle.getIndex(), distro)
    jobs = list()

    for build_file in build_files:
        for os in build_file.get_target_os_names():
            for code_name in build_file.get_target_os_code_names(os):
                for arch in build_file.get_target_arches(os, code_name):
                    jobs.append(build_triggerer(c,
                                                code_name,
                                                arch,
                                                distro,
                                                builders,
                                                oracle.getOrderedRepositories(distro)))
    return jobs

## @brief Trigger the build for the topologically sorted repos
## @param c The Buildmasterconfig
## @param distro Ubuntu distro to build for (for instance, 'precise')
## @param arch Architecture to build for (for instance, 'amd64')
## @param rosdistro ROS distro (for instance, 'groovy')
## @param machines List of machines this can build on.
## @param trigger_pkgs List of set of packages names to trigger.
def build_triggerer(c, distro, arch, rosdistro, machines, ordered_repos):
    f = BuildFactory()
    for repos in ordered_repos:
        f.addStep(
            Trigger(
                schedulerNames = [t.replace('_','-')+'-'+rosdistro+'-'+distro+'-'+arch+'-debtrigger' for t in repos],
                waitForFinish = True,
                alwaysRun=True
            )
        )
    # Add to builders
    c['builders'].append(
        BuilderConfig(
            name = 'build_triggerer'+'_'+rosdistro+'_'+distro+'_'+arch,
            slavenames = machines,
            factory = f
        )
    )
    return 'build_triggerer'+'_'+rosdistro+'_'+distro+'_'+arch

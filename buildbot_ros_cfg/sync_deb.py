from buildbot.config import BuilderConfig
from buildbot.process.factory import BuildFactory
from buildbot.steps.shell import ShellCommand
import yaml
import os

## @brief Sync the local debians with amazon s3 instance
## @param c The Buildmasterconfig
## @param job_name Name for this job
## @param machines List of machines this can build on.
def sync_s3_debians(c, machines):
    with open(os.path.dirname(os.path.realpath(__file__)) + "/spec.yaml") as file:
        spec_list = yaml.full_load(file)

    f = BuildFactory()

    if spec_list["sync_s3"]:
        f.addStep(
            ShellCommand(
                name = 's3-syncing',
                command = ['s3cmd',
                           '--acl-public',
                           '--delete-removed',
                           '--verbose',
                           'sync',
                           spec_list["local_repo_path"],
                           's3://{s3_bucket}'.format(s3_bucket=spec_list["s3_bucket"])]
            )
        )
    # Add to builders
    c['builders'].append(
        BuilderConfig(
            name = 'sync_s3_debians',
            slavenames = machines,
            factory = f
        )
    )
    # return name of builder created
    return 'sync_s3_debians'

#!/usr/bin/env python
'''
Wrapper around git-buildpackage to deal with the change in the way that it
interprets arguments between the version that ships with ubuntu 12.04 and
the version that ships with Ubuntu 14.04.

In older versions of git-buildpackage, the --git-upstream argument could refer
to either a branch or a tag name (bloom uses tags). In recent versions of
git-buildpackage, --git-upstream can only refer to a branch. To get around this,
this script accepts the old style arguments and modifies them to work with the
version of git-buildpackage on this system.

For more information on this issue, see
https://github.com/mikeferguson/buildbot-ros/issues/33
and
https://github.com/ros-infrastructure/bloom/issues/211
'''
import sys
import re
import os
import subprocess
import traceback

def dpkg_parsechangelog(source_dir, fields):
    cmd = ['dpkg-parsechangelog']
    output = subprocess.check_output(cmd, cwd=source_dir)
    values = {}
    for line in output.decode('utf-8').splitlines():
        for field in fields:
            prefix = '%s: ' % field
            if line.startswith(prefix):
                values[field] = line[len(prefix):]
    assert len(fields) == len(values.keys())
    return [values[field] for field in fields]

def _get_package_subfolders(basepath, debian_package_name):
    subfolders = []
    for filename in os.listdir(basepath):
        path = os.path.join(basepath, filename)
        if not os.path.isdir(path):
            continue
        if filename.startswith('%s-' % debian_package_name):
            subfolders.append(path)
    return subfolders

# ensure that one source subfolder exists

debian_pkg, release_version, distro, workdir = sys.argv[1:5]
gbp_args = sys.argv[5:]

try:
    subfolders = _get_package_subfolders(workdir, debian_pkg)
    assert len(subfolders) == 1, subfolders
    source_dir = subfolders[0]
except:
    source_dir=workdir+'/build'

source, version = dpkg_parsechangelog( source_dir, ['Source', 'Version'])

# output package version for job description
print("Package '%s' version: %s" % (debian_pkg, version))


# cmd = ['apt-src', 'import', source, '--location', source_dir, '--version', version]
# print(cmd, source_dir)
# subprocess.check_call(cmd, cwd=source_dir)

# source_dir=workdir+'/build'
# cmd = ['apt-src', 'build', source, '--location', source_dir]

cmd = ['gbp', 'buildpackage', '--git-pbuilder', '--git-upstream-tree=TAG',
      '--git-upstream-tag=debian/{debian_pkg}_{release_version}-0_{distro}'.format(
        debian_pkg=debian_pkg, release_version=release_version, distro=distro)] + gbp_args

print("Invoking '%s' in '%s'" % (' '.join(cmd), source_dir))

try:
    subprocess.check_call(cmd, cwd=source_dir)
except subprocess.CalledProcessError:
    traceback.print_exc()
    sys.exit("""
--------------------------------------------------------------------------------------------------
`{0}` failed.
This is usually because of an error building the package.
The traceback from this failure (just above) is printed for completeness, but you can ignore it.
You should look above `E: Building failed` in the build log for the actual cause of the failure.
--------------------------------------------------------------------------------------------------
""".format(' '.join(cmd)))


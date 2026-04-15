"""Environment state collectors."""

from strata.collectors.base import Collector
from strata.collectors.envvars import EnvVarsCollector
from strata.collectors.processes import ProcessCollector
from strata.collectors.network import NetworkCollector
from strata.collectors.files import FileCollector
from strata.collectors.disk import DiskCollector
from strata.collectors.system import SystemCollector
from strata.collectors.docker import DockerCollector
from strata.collectors.packages import PackageCollector
from strata.collectors.gitrepos import GitReposCollector
from strata.collectors.crontab import CrontabCollector
from strata.collectors.ssh_keys import SSHKeysCollector
from strata.collectors.cloud_config import CloudConfigCollector
from strata.collectors.systemd import SystemdCollector

ALL_COLLECTORS = [
    EnvVarsCollector,
    ProcessCollector,
    NetworkCollector,
    FileCollector,
    DiskCollector,
    SystemCollector,
    DockerCollector,
    PackageCollector,
    GitReposCollector,
    CrontabCollector,
    SSHKeysCollector,
    CloudConfigCollector,
    SystemdCollector,
]

__all__ = [
    "Collector",
    "EnvVarsCollector",
    "ProcessCollector",
    "NetworkCollector",
    "FileCollector",
    "DiskCollector",
    "SystemCollector",
    "DockerCollector",
    "PackageCollector",
    "GitReposCollector",
    "CrontabCollector",
    "SSHKeysCollector",
    "CloudConfigCollector",
    "SystemdCollector",
    "ALL_COLLECTORS",
]

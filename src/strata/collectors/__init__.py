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

ALL_COLLECTORS = [
    EnvVarsCollector,
    ProcessCollector,
    NetworkCollector,
    FileCollector,
    DiskCollector,
    SystemCollector,
    DockerCollector,
    PackageCollector,
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
    "ALL_COLLECTORS",
]

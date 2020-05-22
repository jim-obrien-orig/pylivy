import time
from typing import Any, Dict, List, Optional

from livy.client import LivyClient, Auth
from livy.models import SessionState, SESSION_STATE_FINISHED
from livy.utils import polling_intervals


class LivyBatch:
    """Manages a remote Livy batch and high-level interactions with it.

    The py_files, files, jars and archives arguments are lists of URLs, e.g.
    ["s3://bucket/object", "hdfs://path/to/file", ...] and must be reachable by
    the Spark driver process.  If the provided URL has no scheme, it's
    considered to be relative to the default file system configured in the Livy
    server.

    URLs in the py_files argument are copied to a temporary staging area and
    inserted into Python's sys.path ahead of the standard library paths. This
    allows you to import .py, .zip and .egg files in Python.

    URLs for jars, py_files, files and archives arguments are all copied to the
    same working directory on the Spark cluster.

    The driver_memory and executor_memory arguments have the same format as JVM
    memory strings with a size unit suffix ("k", "m", "g" or "t") (e.g. 512m,
    2g).

    See https://spark.apache.org/docs/latest/configuration.html for more
    information on Spark configuration properties.

    :param url: The URL of the Livy server.
    :param file: File containing the application to execute.
    :param auth: A requests-compatible auth object to use when making requests.
    :param class_name: Application Java/Spark main class.
    :param proxy_user: User to impersonate when starting the session.
    :param jars: URLs of jars to be used in this session.
    :param py_files: URLs of Python files to be used in this session.
    :param files: URLs of files to be used in this session.
    :param driver_memory: Amount of memory to use for the driver process (e.g.
        '512m').
    :param driver_cores: Number of cores to use for the driver process.
    :param executor_memory: Amount of memory to use per executor process (e.g.
        '512m').
    :param executor_cores: Number of cores to use for each executor.
    :param num_executors: Number of executors to launch for this session.
    :param archives: URLs of archives to be used in this session.
    :param queue: The name of the YARN queue to which submitted.
    :param name: The name of this session.
    :param spark_conf: Spark configuration properties.
    :param logger: Passed in logger
    """

    def __init__(
        self,
        url: str,
        file: str,
        auth: Auth = None,
        class_name: str = None,
        args: List[str] = None,
        proxy_user: str = None,
        jars: List[str] = None,
        py_files: List[str] = None,
        files: List[str] = None,
        driver_memory: str = None,
        driver_cores: int = None,
        executor_memory: str = None,
        executor_cores: int = None,
        num_executors: int = None,
        archives: List[str] = None,
        queue: str = None,
        name: str = None,
        spark_conf: Dict[str, Any] = None,
        logger: Any = None
    ) -> None:
        self.client = LivyClient(url, auth)
        self.file = file
        self.class_name = class_name
        self.args = args
        self.proxy_user = proxy_user
        self.jars = jars
        self.py_files = py_files
        self.files = files
        self.driver_memory = driver_memory
        self.driver_cores = driver_cores
        self.executor_memory = executor_memory
        self.executor_cores = executor_cores
        self.num_executors = num_executors
        self.archives = archives
        self.queue = queue
        self.name = name
        self.spark_conf = spark_conf
        self.batch_id: Optional[int] = None
        self.logger = logger

    def start(self) -> None:
        """Create the batch session.

        Unlike LivySession, this does not wait for the session to be ready.
        """
        batch = self.client.create_batch(
            self.file,
            self.class_name,
            self.args,
            self.proxy_user,
            self.jars,
            self.py_files,
            self.files,
            self.driver_memory,
            self.driver_cores,
            self.executor_memory,
            self.executor_cores,
            self.num_executors,
            self.archives,
            self.queue,
            self.name,
            self.spark_conf,
            self.logger
        )
        self.batch_id = batch.batch_id

    def wait(self) -> SessionState:
        """Wait for the batch session to finish."""

        intervals = polling_intervals([0.1, 0.5, 1.0, 3.0], 5.0)

        while True:
            state = self.state
            if state in SESSION_STATE_FINISHED:
                break
            time.sleep(next(intervals))

        return state

    @property
    def state(self) -> SessionState:
        """The state of the managed Spark batch."""
        if self.batch_id is None:
            raise ValueError("batch session not yet started")
        batch = self.client.get_batch(self.batch_id)
        if batch is None:
            raise ValueError(
                "batch session not found - it may have been shut down"
            )
        return batch.state

    def log(self, from_: int = None, size: int = None) -> List[str]:
        """Get logs for this Spark batch.

        :param from_: The line number to start getting logs from.
        :param size: The number of lines of logs to get.
        """
        if self.batch_id is None:
            raise ValueError("batch session not yet started")
        log = self.client.get_batch_log(self.batch_id, from_, size)
        if log is None:
            raise ValueError(
                "batch session not found - it may have been shut down"
            )
        return log.lines

    def kill(self) -> None:
        """Kill the managed Spark batch session."""
        if self.batch_id is not None:
            self.client.delete_batch(self.batch_id)
        self.client.close()

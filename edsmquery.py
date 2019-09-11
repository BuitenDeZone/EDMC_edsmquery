"""
Threaded worker to manage edsm queries.

The EDSMQueries helper will run in it's own thread and perform
a callback when an item on the queue is processed.

Note: By putting this in a module, EDMC will load us sooner than other plugins.
"""
from Queue import Queue, Empty
from threading import Thread, Event
from requests import Session, HTTPError, ConnectionError

from version import VERSION as PLUGIN_VERSION


__version__ = PLUGIN_VERSION

EDSM_CALLBACK_SEQUENCE = '<<EDSMCallback>>'

LOG_CRIT = 1
LOG_ERROR = 2
LOG_WARN = 3
LOG_INFO = 4
LOG_DEBUG = 5

LOG_OUTPUT = {
    1: "CRITICAL",
    2: "ERROR",
    3: "WARNING",
    4: "INFO",
    5: "DEBUG",
    0: "UNKNOWN",
}

LOG_LEVEL = LOG_INFO


def log(max_level, level, prefix, message):
    """Print a log message.

    :param max_level: max level we want to print
    :param level: level of the log message
    :param prefix: prefix to add
    :param message: the message to print
    """
    print_level = LOG_OUTPUT.get(level, 'UNKNOWN')
    if level <= max_level:
        print "{prefix}{level}: {message}".format(prefix=prefix, level=print_level, message=message)


class EDSMQueries(object):
    """Handles queries to EDSM in a queued way."""

    THROTTLE = 5
    API_TIMEOUT = 10
    API_BASE_URL = 'https://www.edsm.net'
    API_COMMANDER_V1 = 'api-commander-v1'
    API_LOGS_V1 = 'api-logs-v1'
    API_JOURNAL_V1 = 'api-journal-v1'
    API_SYSTEM_V1 = 'api-system-v1'
    API_SYSTEMS_V1 = 'api-systems-v1'
    API_STATUS_V1 = 'api-status-v1'

    def __init__(self):
        """Initialize `EDSMQueries`."""

        self.queue = ClearableQueue()
        self.resultQueue = []
        self.callbackWidget = None
        self.thread = None
        self.session = Session()
        self.session.headers['User-Agent'] = "EDMC-Plugin-{plugin_name}/{version}".format(
            plugin_name='edsmquery',
            version=PLUGIN_VERSION,
        )
        self.logLevel = None
        self.logPrefix = 'EDSMQueries > '
        self.interruptEvent = Event()
        self.logLevel = LOG_INFO
        self.logPrefix = "edsmquery > "

    def _log(self, level, message):
        log(self.logLevel, level, self.logPrefix, message)

    def _init_thread(self):
        if self.thread is None:
            self.thread = Thread(target=self.worker, name='edsmquery worker')
            self.thread.daemon = True
        return self.thread

    def start(self, callback_widget=None):
        """
        Start the thread.

        :param callback_widget: When receiving a result, we need to supply a widget to respond to. This is required
        so further processing can be done on the gui mainloop.
        """

        self._log(LOG_DEBUG, "Starting thread....")
        if callback_widget:
            self.callbackWidget = callback_widget

        if self.callbackWidget is None:
            self._log(LOG_ERROR, "Callback widget must be set before starting the thread!")
            return False

        # Reset our interrupt state
        self.interruptEvent.clear()

        # Configure the thread if it does not exist yet.
        if self.thread is None:
            self._init_thread()

        if self.thread.isAlive():
            self._log(LOG_DEBUG, "Thread already started.")
        else:
            self.thread.start()
            self._log(LOG_INFO, "Started thread.")

    def stop(self):
        """Clear queue and stop the thread."""
        if self.thread and self.thread.isAlive():
            self._log(LOG_DEBUG, "Stopping the worker.")
            self._log(LOG_DEBUG, "* Clearing the queue.")
            self.queue.clear()
            self._log(LOG_DEBUG, "* Adding the shutdown marker (None).")
            self.queue.put(None)
            self._log(LOG_DEBUG, "Waiting for worker to exit.")
            # Send an interrupt if we have any THROTTLE waits in place.
            self.interruptEvent.set()
            self.thread.join()
            self._log(LOG_INFO, "Stopped edsmquery.")

        self.thread = None

    def get_response(self):
        """Return the first queued response."""

        if not self.resultQueue:
            return None

        return self.resultQueue.pop(0)

    def request_get(self, api, endpoint, **request_params):
        """Queues a GET request.

        See #_request() for information on parameters.
        """

        self._request(api, endpoint, 'GET', **request_params)

    def request_post(self, api, endpoint, **data):
        """Send out a post request.

        See #_request() for information on parameters.
        """

        self._request(api, endpoint, 'POST', **data)

    def _request(self, api, endpoint, method, **request_params):
        """Add a new request to the queue.

        :param api: api you want to get
        :param endpoint: EDSM's api endpoint you want to hit
        :param method: HTTP method to use.
        :param request_params: additional request parameters.
        """

        self.queue.put((api, endpoint, method, request_params), False)

    def _http_request(self, api, endpoint, method, request_params):
        """Perform the http request to edsm.

        If performing a get request, the request_params are send as such.
        If performing a post request, the request_params is used as
        :param api: api you want to get
        :param endpoint: EDSM's api endpoint you want to hit
        :param method: HTTP method to use.
        :param request_params: additional request parameters.
        """

        url = "{base}/{api}/{endpoint}".format(base=self.API_BASE_URL, api=api, endpoint=endpoint)
        self._log(LOG_DEBUG, "request {method} '{url}'".format(method=method, url=url))
        if method == 'GET':
            session_request = self.session.get(url, params=request_params, timeout=self.API_TIMEOUT)
        elif method == 'POST':
            session_request = self.session.post(url, data=request_params, timeout=self.API_TIMEOUT)

        session_request.raise_for_status()
        return session_request.json()

    def worker(self):
        """Wait for a request to come in.

        Executes the http request and makes the callback with the reply.
        """
        while True:
            request = self.queue.get()
            if request is None:
                break

            (api, endpoint, method, request_params) = request
            reply = None
            retrying = 0
            self._log(LOG_DEBUG, "Performing callback for {api}/{endpoint}".format(api=api, endpoint=endpoint))
            while retrying < 3:
                try:
                    reply = self._http_request(api, endpoint, method, request_params)
                    break
                except ConnectionError, err:
                    self._log(LOG_ERROR, "HTTP Connection error: {err}".format(err=err))
                except HTTPError, err:
                    self._log(LOG_ERROR, "HTTP error occured: {err}".format(err=err))
                retrying += 1

            if reply:
                self.resultQueue.append((request, reply))
                self.callbackWidget.event_generate(EDSM_CALLBACK_SEQUENCE, when='tail')
            else:
                self._log(LOG_ERROR, "Unable to perform request {api}/{endpoint}".format(api=api, endpoint=endpoint))

            if self.THROTTLE > 0:
                self.interruptEvent.wait(self.THROTTLE)
            self.queue.task_done()


class ClearableQueue(Queue):
    """Create a queue that can be cleared."""

    def __init__(self):
        """Initialize the queue."""

        Queue.__init__(self)

    def clear(self):
        """Clear all elements from the queue until we are empty."""

        try:
            while True:
                self.get_nowait()
        except Empty:
            pass


EDSM_QUERIES = EDSMQueries()

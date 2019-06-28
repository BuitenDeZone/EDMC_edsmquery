"""EDSMQuery Plugin."""

import sys
from pprint import pformat

import plug

from version import VERSION, NAME as PLUGIN_NAME
import edsmquery
from edsmquery import LOG_DEBUG, LOG_INFO

this = sys.modules[__name__]  # For holding module globals

LOG_LEVEL = LOG_INFO
LOG_PREFIX = "{plugin_name} load > ".format(plugin_name=PLUGIN_NAME)


def log(level, message):
    """Print a log message.

    :param level: Log level of the message
    :param message: The message to print
    """
    edsmquery.log(LOG_LEVEL, level, LOG_PREFIX, message)


def plugin_start():
    """Perform plugin initialization."""

    #                |
    # . . .,---.,---.|__/ ,---.,---.
    # | | ||   ||    |  \ |---'|
    # `-'-'`---'`    `   ``---'`
    this.edsmQueries = edsmquery.EDSM_QUERIES

    print("Loaded {name} (v{version}).".format(name=PLUGIN_NAME, version=VERSION))
    return PLUGIN_NAME


def plugin_stop():
    """Stop and cleanup all running threads."""

    this.edsmQueries.stop()


def plugin_app(parent):
    """
    Initialize our frame to display our matches.

    We do not return it because that kinda messes with how EDMC handles
    frames from plugins. It is lazy loaded later on.
    """

    parent.bind('<<EDSMCallback>>', _edsm_callback_received)
    this.edsmQueries.callbackWidget = parent
    # this.edsmQueries.start(parent)


def _edsm_callback_received(_event=None):
    """Proxy callbacks to plugins that support them.

    You should filter the responses you need out yourself.
    You can pre-filter specific api's and endpoints by implementing
    specific callbacks for each:

        * edsm_querier_response_api_system_v1_bodies: will only receive api-system-v1 bodies responses.
        * edsm_querier_response_api_system_v1: will receive all api-system-v1 responses.
        * edsm_querier_response: will receive all responses.


    If any of these returns `True`, the remaining more generic methods will be skipped for your plugin.
    """

    log(LOG_DEBUG, 'edsm callback received')
    while True:
        response = this.edsmQueries.get_response()
        if response is None:
            break

        # LOGGER.debug(this, 'response: {resp}'.format(resp=pformat(response)))
        (request, reply) = response
        (api, endpoint, _method, _request_params) = request

        api_callbacks = [
            'edsm_querier_response_{api}_{endpoint}'.format(
                api=api.replace('-', '_'),
                endpoint=endpoint,
            ),
            'edsm_querier_response_{api}'.format(api=api.replace('-', '_')),
            'edsm_querier_response',
        ]

        for plugin in plug.PLUGINS:
            for api_callback in api_callbacks:

                log(LOG_DEBUG, "checking for function: '{func}' on {plugin}".format(
                    func=api_callback,
                    plugin=plugin.name,
                ))
                log(LOG_DEBUG, "plugin: {pl}".format(pl=pformat(plugin)))
                if hasattr(plugin.module, api_callback):
                    response = plug.invoke(plugin.name, None, api_callback, request, reply)
                    log(LOG_DEBUG, 'calling {func} on {plugin}: {response}'.format(
                        func=api_callback,
                        plugin=plugin,
                        response=str(response),
                    ))
                    if response is True:
                        break

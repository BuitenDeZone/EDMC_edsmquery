"""EDSMQuery Plugin."""

# EDSMQuery
# ignore the relative imports here. Without them, my IDE does not like these references.
from version import VERSION
from edsmquery import LOG_DEBUG, LOG_INFO, log as edsmquery_log
from edsmquery import EDSM_QUERIES, EDSM_CALLBACK_SEQUENCE

# System
import sys
from pprint import pformat

# EDMarketConnector: Core
import plug
from monitor import monitor
from config import config

# EDMarketConnector: Preferences UI
import Tkinter as tk
import myNotebook as nb

# L10N
import l10n
import functools
_ = functools.partial(l10n.Translations.translate, context=__file__)


this = sys.modules[__name__]  # For holding module globals

LOG_LEVEL = LOG_INFO  # Change this to LOG_DEBUG if you are debugging.
LOG_PREFIX = "edsmquery: load.py > "


def log(level, message):
    """Print a log message.

    :param level: Log level of the message
    :param message: The message to print
    """
    edsmquery_log(LOG_LEVEL, level, LOG_PREFIX, message)


def plugin_start(_plugin_dir):
    """Perform plugin initialization."""

    #                |
    # . . .,---.,---.|__/ ,---.,---.
    # | | ||   ||    |  \ |---'|
    # `-'-'`---'`    `   ``---'`
    this.lastEDSMScan = None
    this.edsmQueries = EDSM_QUERIES

    # this.updateBodies = tk.IntVar(value=)

    log(LOG_INFO, "{name} (v{version}) initialized.".format(name='edsmquery', version=VERSION))
    return 'edsmquery'


def plugin_stop():
    """Stop and cleanup all running threads."""

    this.edsmQueries.stop()


def plugin_app(parent):
    """Configure the EDSMQuerier callbacks."""
    this.edsmQueries.callbackWidget = parent
    # Bind to events thrown by edsmquery
    parent.bind(EDSM_CALLBACK_SEQUENCE, _edsm_callback_received)
    # this.edsmQueries.start(parent)


def plugin_prefs(parent, _cmdr, _is_beta):
    """Return a Tk Frame for adding to the EDMC settings dialog."""

    this.disable_auto_edsm_system_bodies = tk.IntVar(value=config.getint("edsmquery.disable_auto_edsm_system_bodies"))
    system_bodies_api = EDSM_QUERIES.API_SYSTEM_V1
    system_bodies_endpoint = EDSM_QUERIES.API_SYSTEM_V1__BODIES

    label_system_bodies_api_checkbutton = _("Disable auto EDSM system/bodies request for known systems.")
    label_system_bodies_api_warn_text = _("Warning: Plugins listed below may fail to work correctly.")

    # Todo: find plugins that DO depend on this functionality
    frame = nb.Frame(parent)
    nb.Checkbutton(frame, text=label_system_bodies_api_checkbutton, variable=this.disable_auto_edsm_system_bodies)\
        .grid(sticky=tk.W)
    nb.Label(frame, text=label_system_bodies_api_warn_text, justify=tk.LEFT)\
        .grid(sticky=tk.W)

    # List all plugins that use callback hooks.
    in_use_callbacks = _edsmquery_plugins_usage_callback(system_bodies_api, system_bodies_endpoint)
    if len(in_use_callbacks) > 0:
        for plugin in in_use_callbacks.keys():
            label_plugin = "* {plugin_name}: {found_callbacks}".format(
                plugin_name=plugin.name,
                found_callbacks=", ".join(in_use_callbacks[plugin]),
            )
            nb.Label(frame, text=label_plugin, justify=tk.LEFT)\
                .grid(sticky=tk.W, padx=20)
    else:
        nb.Label(frame, text=_("No triggers found in currently installed plugins."), justify=tk.LEFT)\
            .grid(sticky=tk.W, padx=20)

    return frame


def prefs_changed(_cmdr, _is_beta):
    """Save settings."""
    config.set('edsmquery.disable_auto_edsm_system_bodies', this.disable_auto_edsm_system_bodies.get())


def _edsmquery_callbacks(api, endpoint):
    return [
        'edsm_querier_response_{api}_{endpoint}'.format(
            api=api.replace('-', '_'),
            endpoint=endpoint,
        ),
        'edsm_querier_response_{api}'.format(api=api.replace('-', '_')),
        'edsm_querier_response',
    ]


def _edsmquery_plugins_usage_callback(api, endpoint):
    """List all plugins that use an api/endpoint."""

    usage = dict()
    for plugin in plug.PLUGINS:
        for api_callback in _edsmquery_callbacks(api, endpoint):
            log(LOG_DEBUG, "checking for function: '{func}' on {plugin}".format(
                func=api_callback,
                plugin=plugin.name,
            ))
            if hasattr(plugin.module, api_callback):
                usage.setdefault(plugin, [])
                usage[plugin].append(api_callback)

    return usage


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

        api_callbacks = _edsmquery_callbacks(api, endpoint)

        for plugin in plug.PLUGINS:
            # We loop over the plugins first so that each plugin can interrupt further callbacks
            # from being called only to itself.
            for api_callback in api_callbacks:
                log(LOG_DEBUG, "checking for function: '{func}' on {plugin}".format(
                    func=api_callback,
                    plugin=plugin.name,
                ))
                if hasattr(plugin.module, api_callback):
                    response = plug.invoke(plugin.name, None, api_callback, request, reply)
                    log(LOG_DEBUG, 'calling {func} on {plugin}: {response}'.format(
                        func=api_callback,
                        plugin=plugin,
                        response=str(response),
                    ))
                    if response is True:
                        break


# This only gets us events from the edsm plugin
def edsm_notify_system(reply):
    """
    Handle an event sent by EDMarketConnector/plugins/edsm.

    When an existing system is encountered, trigger an update from EDSM.
    :param reply:
    """
    log(LOG_DEBUG, "Processing edsm notify event: {event}".format(event=pformat(reply)))
    if not reply:
        return
    elif reply['msgnum'] // 100 not in (1, 4):
        return
    elif reply.get('systemCreated'):
        return
    elif this.lastEDSMScan and this.lastEDSMScan == monitor.system:
        return
    else:
        this.lastEDSMScan = monitor.system
        if config.getint('edsmquery.disable_auto_edsm_system_bodies') == 0:
            EDSM_QUERIES.request_get(
                EDSM_QUERIES.API_SYSTEM_V1,
                EDSM_QUERIES.API_SYSTEM_V1__BODIES,
                systemName=this.lastEDSMScan,
            )

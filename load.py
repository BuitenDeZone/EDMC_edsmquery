"""EDSMQuery Plugin."""

# EDSMQuery
# ignore the relative imports here. Without them, my IDE does not like these references.

from version import VERSION
from fields import EDSM_CALLBACK_SEQUENCE
from fields import LOG_DEBUG, LOG_INFO, LOG_OUTPUT
from fields import JOURNAL_ENTRY_FIELD_EVENT, JOURNAL_ENTRY_VALUE_EVENT_FSS_DISCOVERY_SCAN, \
    JOURNAL_ENTRY_FIELD_BODY_COUNT, JOURNAL_ENTRY_VALUE_EVENT_SCAN, JOURNAL_ENTRY_FIELD_SCAN_TYPE, \
    JOURNAL_ENTRY_VALUE_SCAN_TYPE_AUTOSCAN, JOURNAL_ENTRY_VALUE_SCAN_TYPE_DETAILED, JOURNAL_ENTRY_FIELD_BODY_NAME, \
    LOG_WARN, EDSM_RESPONSE_FIELD_BODY_COUNT, EDSM_RESPONSE_FIELD_BODIES, EDSM_RESPONSE_FIELD_NAME

from edsmquery.edsmquery import EDSM_QUERIES

# System
import sys
from pprint import pformat

# EDMarketConnector: Core
import plug
from monitor import monitor
from config import config

# EDMarketConnector: UI
import myNotebook as nb

# L10N
import l10n
import functools

# Python 3
import tkinter as tk
from tkinter import ttk

_ = functools.partial(l10n.Translations.translate, context=__file__)

this = sys.modules[__name__]  # For holding module globals

this.LOG_LEVEL = LOG_INFO  # Change this to LOG_DEBUG if you are debugging.
this.LOG_PREFIX = "edsmquery: load.py > "

# Configuration keys used. Some are defaulted at plugin startup (if needed) to workaround getint() and unset values.
CONFIG_KEY_DISABLE_AUTO_SYSTEM_BODIES = 'edsmquery.disable_auto_edsm_system_bodies'
CONFIG_KEY_SHOW_SCAN_PROGRESS = 'edsmquery.show_edsm_bodies_scan_progress'
CONFIG_KEY_HIDE_COMPLETE_SCAN_PROGRESS = 'edsmquery.hide_scan_progress_if_complete'

# -1: disable, 0: un-initialized, 1: enabled.
CONFIG_DEFAULTS = {
    CONFIG_KEY_DISABLE_AUTO_SYSTEM_BODIES: -1,
    CONFIG_KEY_SHOW_SCAN_PROGRESS: -1,
    CONFIG_KEY_HIDE_COMPLETE_SCAN_PROGRESS: 1,
}


def log(level, message):
    """Print a log message.

    :param level: Log level of the message
    :param message: The message to print
    """
    print_level = LOG_OUTPUT.get(level, 'UNKNOWN')
    if level <= this.LOG_LEVEL:
        print("{prefix}{level}: {message}".format(prefix=this.LOG_PREFIX, level=print_level, message=message))


def plugin_start3(plugin_dir):
    """Python 3 compat."""
    return plugin_start(plugin_dir)


def plugin_start(_plugin_dir):
    """Perform plugin initialization."""

    #                |
    # . . .,---.,---.|__/ ,---.,---.
    # | | ||   ||    |  \ |---'|
    # `-'-'`---'`    `   ``---'`

    this.edsmQueries = EDSM_QUERIES  # Background threading
    this.lastEDSMRequest = None  # System name of the last request we sent out to prevent hammering.

    # Used by our progress bar
    this.currentSystem = None
    this.currentSystemBodyCount = 0
    this.currentKnownBodies = []

    # Default configuration.
    for configkey in CONFIG_DEFAULTS.keys():
        if config.get(configkey) is None:
            log(LOG_DEBUG, "Defaulting config key {key} to {value}".format(
                key=configkey, value=str(CONFIG_DEFAULTS[configkey])))
            config.set(configkey, str(CONFIG_DEFAULTS[configkey]))

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
    __initialize_progress_frame(parent)
    __update_progress_frame()
    return this.wrapped_parent


def plugin_prefs(parent, _cmdr, _is_beta):
    """Return a Tk Frame for adding to the EDMC settings dialog."""
    # used IntVars for configuration settings.
    this.disable_auto_edsm_system_bodies = tk.IntVar(value=int(config.get(CONFIG_KEY_DISABLE_AUTO_SYSTEM_BODIES)))
    this.show_edsm_system_scan_progress = tk.IntVar(value=int(config.get(CONFIG_KEY_SHOW_SCAN_PROGRESS)))
    this.hide_complete_scan_progress = tk.IntVar(value=int(config.get(CONFIG_KEY_HIDE_COMPLETE_SCAN_PROGRESS)))

    text_show_edsm_system_scan_progress = _("Show EDSM scanned bodies progress for the current system.")
    text_hide_complete_scan_progress = _("Hide the progressbar if all bodies have been scanned.")

    text_advanced_options = _("Advanced preferences:")
    text_system_bodies_api_checkbutton = _("Disable auto EDSM system/bodies request for known systems.")
    text_system_bodies_api_warn_plugins = _("Warning: Plugins listed below may fail to work correctly, if disabled.")

    frame = nb.Frame(parent)
    nb.Checkbutton(frame, text=text_show_edsm_system_scan_progress, variable=this.show_edsm_system_scan_progress,
                   offvalue=-1, onvalue=1) \
        .grid(sticky=tk.W)
    nb.Checkbutton(frame, text=text_hide_complete_scan_progress, variable=this.hide_complete_scan_progress,
                   offvalue=-1, onvalue=1) \
        .grid(sticky=tk.W)
    ttk.Separator(frame).grid(sticky=tk.E + tk.W, padx=0, pady=5)
    nb.Label(frame, text=text_advanced_options, justify=tk.LEFT) \
        .grid(sticky=tk.W, pady=5)
    nb.Checkbutton(frame, text=text_system_bodies_api_checkbutton,
                   variable=this.disable_auto_edsm_system_bodies,
                   offvalue=-1, onvalue=1) \
        .grid(sticky=tk.W)
    nb.Label(frame, text=text_system_bodies_api_warn_plugins, justify=tk.LEFT) \
        .grid(sticky=tk.W)

    # List all plugins that use callback hooks (api-system-v1 / bodies).
    in_use_callbacks = _edsmquery_plugins_usage_callback(EDSM_QUERIES.API_SYSTEM_V1, EDSM_QUERIES.API_SYSTEM_V1__BODIES)
    if len(in_use_callbacks) > 0:
        for plugin in in_use_callbacks.keys():
            label_plugin = "* {plugin_name}: {found_callbacks}".format(
                plugin_name=plugin.name,
                found_callbacks=", ".join(in_use_callbacks[plugin]),
            )
            nb.Label(frame, text=label_plugin, justify=tk.LEFT) \
                .grid(sticky=tk.W, padx=20)
    else:
        nb.Label(frame, text=_("No triggers found in currently installed plugins."), justify=tk.LEFT) \
            .grid(sticky=tk.W, padx=20)

    return frame


def prefs_changed(_cmdr, _is_beta):
    """Save settings."""
    config.set(CONFIG_KEY_DISABLE_AUTO_SYSTEM_BODIES, str(this.disable_auto_edsm_system_bodies.get()))
    config.set(CONFIG_KEY_SHOW_SCAN_PROGRESS, str(this.show_edsm_system_scan_progress.get()))
    config.set(CONFIG_KEY_HIDE_COMPLETE_SCAN_PROGRESS, str(this.hide_complete_scan_progress.get()))
    __update_progress_frame()


def __initialize_progress_frame(parent):
    this.system_progress = tk.IntVar(value=0)
    this.wrapped_parent = tk.Frame(parent)
    this.wrapped_parent.grid(columnspan=2, sticky=tk.N + tk.W + tk.E + tk.S)

    this.progress_frame = tk.Frame(this.wrapped_parent)
    this.style = ttk.Style()
    this.style.theme_use('default')
    this.style.configure("red.Horizontal.TProgressbar",
                         thickness=10,
                         barsize=10,
                         pbarrelief=tk.FLAT,
                         troughrelief=tk.SOLID,
                         troughcolor='black',
                         background=config.get('dark_text'),
                         )

    this.edsm_progress_label = tk.Label(this.progress_frame, text=_("EDSM scanned:"), foreground="white")
    this.system_progress_bar = ttk.Progressbar(this.progress_frame, mode="determinate", variable=this.system_progress,
                                               style="red.Horizontal.TProgressbar")

    this.system_progress_label = tk.Label(this.progress_frame, text="[?/?]")

    this.edsm_progress_label.grid(column=0, row=0)
    this.system_progress_bar.grid(column=1, row=0, sticky=tk.E + tk.W)
    this.system_progress_label.grid(column=2, row=0)

    this.progress_frame.grid(columnspan=2, sticky=tk.N + tk.W + tk.E + tk.S)
    this.progress_frame.grid_columnconfigure(0, weight=0)
    this.progress_frame.grid_columnconfigure(1, weight=5)
    this.progress_frame.grid_columnconfigure(2, weight=0)
    this.wrapped_parent.grid_columnconfigure(0, weight=1)
    return this.wrapped_parent


def __update_progress_frame():
    if config.getint(CONFIG_KEY_SHOW_SCAN_PROGRESS) < 0:
        this.progress_frame.grid_forget()
    else:
        if this.currentSystemBodyCount == 0:
            this.system_progress.set(0)
            this.system_progress_label.config(text='[?/?]')
            if int(config.get(CONFIG_KEY_HIDE_COMPLETE_SCAN_PROGRESS)) > 0 and len(this.currentKnownBodies) == 0:
                this.progress_frame.grid_forget()
            else:
                this.progress_frame.grid(columnspan=2, sticky=tk.N + tk.W + tk.E + tk.S)
        else:
            progress = len(this.currentKnownBodies) * 100 / this.currentSystemBodyCount
            this.system_progress.set(progress)
            this.system_progress_label["text"] = "{done}/{total}".format(
                done=len(this.currentKnownBodies),
                total=this.currentSystemBodyCount,
            )
            if int(config.get(CONFIG_KEY_HIDE_COMPLETE_SCAN_PROGRESS)) > 0 and progress >= 100:
                this.progress_frame.grid_forget()
            else:
                this.progress_frame.grid(columnspan=2, sticky=tk.N + tk.W + tk.E + tk.S)

    this.wrapped_parent.update()


def journal_entry(_cmdr, _is_beta, system, _station, entry, _state):
    """Process EDMarketConnector journal entry."""
    need_ui_update = False
    log(LOG_DEBUG, "Journal entry received: {event}".format(event=entry['event']))
    log(LOG_DEBUG, "  event: {event}".format(event=pformat(entry)))

    if this.currentSystem != system:
        this.currentSystemBodyCount = 0
        this.currentKnownBodies = []
        this.currentSystem = system
        need_ui_update = True
        log(LOG_WARN, "New system entered. Clearing all values.")

    # discovery scan
    if entry[JOURNAL_ENTRY_FIELD_EVENT] == JOURNAL_ENTRY_VALUE_EVENT_FSS_DISCOVERY_SCAN \
            and this.currentSystemBodyCount != entry[JOURNAL_ENTRY_FIELD_BODY_COUNT]:
        log(LOG_DEBUG, "Discovery Scan detected")
        this.currentSystemBodyCount = entry[JOURNAL_ENTRY_FIELD_BODY_COUNT]
        need_ui_update = True

    # planet scan / auto scan
    if entry[JOURNAL_ENTRY_FIELD_EVENT] == JOURNAL_ENTRY_VALUE_EVENT_SCAN \
            and entry[JOURNAL_ENTRY_FIELD_SCAN_TYPE] in [JOURNAL_ENTRY_VALUE_SCAN_TYPE_AUTOSCAN,
                                                         JOURNAL_ENTRY_VALUE_SCAN_TYPE_DETAILED]:

        log(LOG_DEBUG, "Scanned body: {event}".format(event=pformat(entry)))
        body_name = entry[JOURNAL_ENTRY_FIELD_BODY_NAME]
        if 'belt cluster' not in body_name.lower() and body_name not in this.currentKnownBodies:
            this.currentKnownBodies.append(body_name)
            need_ui_update = True

    if need_ui_update:
        __update_progress_frame()


def edsm_querier_response_api_system_v1_bodies(request, response):
    """Handle EDSM api-system-v1/bodies responses."""
    log(LOG_DEBUG, "Self received system bodies responses.")
    (_api, _endpoint, _method, _params) = request
    need_ui_update = False
    if response:
        log(LOG_DEBUG, "EDSM bodies: {event}".format(event=pformat(response)))
        system = response['name']
        if monitor.system != system:
            log(LOG_WARN, "systems disagree on where we are!")
            log(LOG_DEBUG, "  + system: {system}".format(system=system))
            log(LOG_DEBUG, "  + monitor.system: {system}".format(system=monitor.system))
            log(LOG_DEBUG, "  + this.currentSystem: {system}".format(system=this.currentSystem))
            # woops, bit late or something?
            return True

        if this.currentSystem != system:
            this.currentSystem = system
            this.currentKnownBodies = []
            this.currentSystemBodyCount = 0

        body_count = response.get(EDSM_RESPONSE_FIELD_BODY_COUNT, None)
        log(LOG_DEBUG, "EDSM.bodyCount: {count}".format(count=body_count))
        if body_count is not None:
            if this.currentSystemBodyCount != body_count:
                need_ui_update = True
            this.currentSystemBodyCount = body_count

        bodies = response.get(EDSM_RESPONSE_FIELD_BODIES, [])

        for body in bodies:
            planet = body[EDSM_RESPONSE_FIELD_NAME]
            log(LOG_DEBUG, "EDSM: planet: {planet}".format(planet=planet))
            if planet not in this.currentKnownBodies:
                this.currentKnownBodies.append(planet)
                need_ui_update = True

        log(LOG_DEBUG, "EDSM: Current bodies after import: {list}".format(list=", ".join(this.currentKnownBodies)))

    if need_ui_update:
        __update_progress_frame()

#  ___       _                        _
# |_ _|_ __ | |_ ___ _ __ _ __   __ _| |___
#  | || '_ \| __/ _ \ '__| '_ \ / _` | / __|
#  | || | | | ||  __/ |  | | | | (_| | \__ \
# |___|_| |_|\__\___|_|  |_| |_|\__,_|_|___/
# ------------------------------------------
# The code below is responsible for responding to processed requests
# and pass them through to other plugins.


def _edsmquery_callbacks(api, endpoint):
    """Return the different callbacks to perform for a certain api/endpoint combination.

    They are ordered more specific first.
    """
    return [
        'edsm_querier_response_{api}_{endpoint}'.format(
            api=api.replace('-', '_'),
            endpoint=endpoint,
        ),
        'edsm_querier_response_{api}'.format(api=api.replace('-', '_')),
        'edsm_querier_response',
    ]


def _edsmquery_plugins_usage_callback(api, endpoint):
    """
    List all plugins that use an api/endpoint.

    The returned result is a dict with plugins mapped to the found callbacks.
    """

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
    # do not spam edsm if we have already sent out a request for the system we are in.
    elif this.lastEDSMRequest and this.lastEDSMRequest == monitor.system:
        return
    else:
        this.lastEDSMRequest = monitor.system
        if int(config.get(CONFIG_KEY_DISABLE_AUTO_SYSTEM_BODIES)) < 0:
            EDSM_QUERIES.request_get(
                EDSM_QUERIES.API_SYSTEM_V1,
                EDSM_QUERIES.API_SYSTEM_V1__BODIES,
                systemName=this.lastEDSMRequest,
            )

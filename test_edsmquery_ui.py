"""Test EDSMQueries."""

import sys
import json
import Tkinter as tk
import tkFont

from edsmquery import EDSM_QUERIES, LOG_DEBUG

this = sys.modules[__name__]  # For holding module globals


class Application(tk.Frame):
    """Test application."""

    def __init__(self, master=None):
        """Initialize the application."""

        tk.Frame.__init__(self, master, width=400, height=300)
        self.master = master
        self.queries = EDSM_QUERIES
        self.resultRequest = None
        self.resultOutput = None
        EDSM_QUERIES.logLevel = LOG_DEBUG
        self.queries.start(master)  # used for callbacks
        self.create_widgets()
        self.grid()
        master.protocol("WM_DELETE_WINDOW", self.onexit)

    def create_widgets(self):
        """Create us some widgets."""

        output_font = tkFont.Font(family="Courier", size=9)
        label_font = tkFont.Font(weight=tkFont.BOLD, size=9)

        label_request = tk.Label(self, text="request:", justify=tk.LEFT, font=label_font)
        label_request.grid(sticky=tk.W)
        self.resultRequest = tk.Label(self, text="request", justify=tk.LEFT, font=output_font)
        self.resultRequest.grid(sticky=tk.W)
        label_output = tk.Label(self, text="response:", justify=tk.LEFT, font=label_font)
        label_output.grid(sticky=tk.W)
        self.resultOutput = tk.Label(self, text="response", justify=tk.LEFT, font=output_font)
        self.resultOutput.grid(sticky=tk.W)

    def onexit(self):
        """
        Clean up.

        Called on exit of the application.
        """
        try:
            self.queries.stop()
            print("Bye!")
        finally:
            self.master.destroy()


def callback(request, response):
    """Process callbacks."""

    (api, endpoint, _method, _request_params) = request

    APP.resultRequest.config(text=json.dumps(request, indent=2, sort_keys=True))
    if api == EDSM_QUERIES.API_SYSTEM_V1 and endpoint == 'bodies':
        if response:
            this.lastScanned = response['name']
            this.currentState = dict()
            this.currentState = {
                "system": response['name'],
                "body_count": response['bodyCount'],
                "scanned": len(response['bodies']),
            }

            dump = json.dumps(this.currentState, indent=2, sort_keys=True)
            APP.resultOutput.config(text=dump)
        else:
            dump = json.dumps(response, indent=2, sort_keys=True)
            APP.resultOutput.config(text=dump)
    else:
        dump = json.dumps(response, indent=2, sort_keys=True)
        APP.resultOutput.config(text=dump)


def eventfull_callback(_event=None):
    """Catch EDSMCallback callback."""

    (request, reply) = APP.queries.get_response()
    callback(request, reply)


def make_requests():
    """Queue some requests."""

    APP.queries.request_get(EDSM_QUERIES.API_STATUS_V1, 'elite-server')
    # APP.queries.request_get(EDSM_QUERIES.API_STATUS_V1, 'elite-server')
    # APP.queries.request_get(EDSM_QUERIES.API_STATUS_V1, 'elite-server')
    # APP.queries.request_get(EDSM_QUERIES.API_SYSTEM_V1, 'bodies', systemName="Myrielk NF-N c20-121")


ROOT = tk.Tk()
APP = Application(master=ROOT)
ROOT.bind_all('<<EDSMCallback>>', eventfull_callback)
EDSM_QUERIES.start(ROOT)
APP.after(1000, make_requests)
APP.mainloop()

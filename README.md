# EDMarketConnector EDSM Query plugin

Sends queries to EDSM. This plugin is meant to be used by other plugins.

## Using in your plugin

Make sure that edsmquery is in the EDMarketConnector's plugin folder.

Minimal plugin `load.py`:    
```python
from edsmquery import EDSM_QUERIES


def plugin_app(parent):
    """Initialize the UI."""
    # Force start or initialization of EDSMQueries
    EDSM_QUERIES.start(parent)


def edsm_querier_response(request, response):
    """Process events produced by EDSMQuerier.
    
    You can use the request to inspect if this event is valuable to you.
    :param request: A tuple with the initial request: (api, endpoint, method, request_params)
    :param response: The response (parsed json).
    """
    pass
```

## Callback parameters
### `request`

```python
(api, endpoint, method, request_params) = request
```

The request contains all information used to make the request.
* `api`: the edsm api that was queried. i.e. `api-system-v1`.
* `endpoint`: the edsm api endpoint that was called. i.e. `bodies`
* `method`: HTTP method that was used. i.e. `GET`
* `request_params`: The used request parameters (or data for `POST`s).
 
### `response`

The response depends on the requested endpoint. If nothing goes wrong, it is the exact reply 
from EDSM, `json` parsed.

## Callback methods

To narrow down which events you need to process (or skip), you can implement different api/endpoint
specific callback functions in your plugin. These are called, in order, from most-specific to
the general `edsm_querier_response` callback which gets all events.

* `edsm_querier_response_<api>_<endpoint>`
* `edsm_querier_response_<api>`
* `edsm_querier_response`

The `api` and `endpoint` placeholders here will be replaced by the matching api and endpoint
but with the names sanitized (dashes are replaced with underscores).

```python
def edsm_querier_response_api_system_v1_bodies(request, response):
    # Called with information on bodies for a system.
    pass
    
def edsm_querier_response_api_system_v1(request, response):
    # This will never be called for system/bodies calls since a more
    # specific implementation is in place.
    pass
    
def edsm_querier_api_status_v1(request, response):
    pass
```

## License

[GPL-3.0](https://choosealicense.com/licenses/gpl-3.0/)
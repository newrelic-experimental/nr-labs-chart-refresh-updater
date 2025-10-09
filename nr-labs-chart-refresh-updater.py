# Built-in imports
from email import errors
import logging
import json
import optparse
import os
import sys
import traceback
from typing import List, Any
from urllib.request import Request, urlopen


# Setup logging to stdout with a decent format
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
    level=logging.INFO
)


# Create the global logger
logger = logging.getLogger(__name__)


# The US GraphQL endpoint
GRAPHQL_US_URL = 'https://api.newrelic.com/graphql'


# The default configuration file name
DEFAULT_CONFIG_FILE = 'config.json'


# -----------------------------------------------------------------------------
# Error classes
# -----------------------------------------------------------------------------


class GraphQLApiError(Exception):
    """Exception raised for GraphQL errors.

    :param message: A message describing the error that occurred.
    :type message: str
    :param status: The status code returned by the API.
    :type status: int
    :param reason: The reason returned by the API.
    :type reason: str
    """

    def __init__(
        self,
        message: str,
        status: int,
        reason: str
    ):
        """The constructor method.
        """

        super().__init__(message)
        self.status = status
        self.reason = reason


class DashboardNotFoundError(Exception):
    """Exception raised for dashboard not found errors.

    :param message: A message describing the error that occurred.
    :type message: str
    """

    def __init__(
        self,
        message: str,
    ):
        """The constructor method.
        """

        super().__init__(message)


class DashboardValidationError(Exception):
    """Exception raised for dashboard validation errors.

    :param message: A message describing the error that occurred.
    :type message: str
    """

    def __init__(
        self,
        message: str,
    ):
        """The constructor method.
        """

        super().__init__(message)


# -----------------------------------------------------------------------------
# Helper functions
# -----------------------------------------------------------------------------


def _get_nested_helper(val: Any, arr: List[str] = [], index: int = 0) -> Any:
    """Recursive helper used by get_nested to safely get nested attributes.

    :param val: A value.
    :type val: Any
    :param arr: The list of "path" segments, defaults to the empty list.
    :type arr: list[str], optional
    :param index: The index of the current segment to examine, defaults to 0.
    :type index: int, optional
    :returns: False if we pass the last segment or the current value is not a
        dictionary, otherwise the value at index.
    :rtype: Any or bool
    """

    if index == len(arr):
        return False
    elif type(val) == dict:
        key = arr[index]
        if index == len(arr) - 1:
            return val[key] if key in val else None
        return _get_nested_helper(val[key], arr, index + 1) if key in val else None
    return False


def get_nested(d: dict, path: str) -> Any:
    """Safely get a value by "path" nested within dictionaries in d.

    :param d: A dictionary.
    :type d: dict
    :param path: A "path" of attribute names separated by ".".
    :type path: str
    :returns: False if we pass the last segment or the current value is not a
        dictionary, otherwise the value at index.
    :rtype: Any or bool
    """

    return _get_nested_helper(d, path.split('.'))


# -----------------------------------------------------------------------------
# Config functions
# -----------------------------------------------------------------------------


def parse_args() -> optparse.Values:
    """Parse command line arguments and return the parsed values.

    :returns: The parsed command line arguments.
    :rtype: optparse.Values
    """

    # Create the parser object
    parser = optparse.OptionParser()

    # Populate options
    parser.add_option(
        '-f',
        '--config_file',
        default=DEFAULT_CONFIG_FILE,
        help='name of configuration file',
    )

    parser.add_option(
        '-d',
        '--debug',
        action='store_true',
        help='enable debug logging',
    )

    # Parse arguments
    (values, _) = parser.parse_args()

    return values


def load_config(config_path: str) -> dict:
    """Load the configuration file from the given path.

    :param config_path: The path to the configuration file.
    :type config_path: str
    :raises FileNotFoundError: If the configuration file does not exist.
    :raises json.JSONDecodeError: If the configuration file is not valid JSON.
    :return: The loaded configuration as a dictionary.
    :rtype: dict
    """

    if not os.path.exists(config_path):
        raise FileNotFoundError(f'config file {config_path} not found')

    with open(config_path) as stream:
        return json.load(stream)


# -----------------------------------------------------------------------------
# GraphQL functions
# -----------------------------------------------------------------------------


def build_graphql_headers(api_key: str, headers: dict = {}) -> dict:
    """Return a dictionary containing HTTP headers for a Nerdgraph call.

    If specified, the additional headers will be merged into the default
    headers.

    :param api_key: The User API key to use.
    :type api_key: str
    :param headers: Additional headers to send, defaults to {}.
    :type headers: dict, optional
    :return: A dictionary containing HTTP headers for a Nerdgraph call.
    :rtype: dict
    """

    all_headers = {
        'Api-Key': api_key,
        'Content-Type': 'application/json'
    }

    all_headers.update(headers)

    return all_headers


def post_graphql(
    api_key: str,
    payload: dict,
    headers: dict = {},
) -> dict:
    """Make the actual GraphQL POST call using the given payload.

    :param api_key: The User API key to use.
    :type api_key: str
    :param payload: The payload to send, as a dict.
    :type payload: dict
    :param headers: Additional headers to send, defaults to {}.
    :type headers: dict, optional
    :raises GraphQLApiError: if the response code of the POST call is not
        a 2XX code or if the `errors` property of the parsed GraphQL
        response is present.
    :return: The `data` property of the parsed GraphQL response as a dict.
    :rtype: dict
    """

    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(json.dumps(payload, indent=2))

    request = Request(
        GRAPHQL_US_URL,
        data=json.dumps(payload).encode('utf-8'),
        headers=build_graphql_headers(api_key, headers),
    )

    with urlopen(
        request,
        timeout=30,
    ) as response:
        status = response.status
        reason = response.reason

        if status != 200:
            logger.error(
                f'GraphQL request failed with status: {status}, reason: {reason}',
            )
            raise GraphQLApiError(
                f'GraphQL request failed with status: {status}, reason: {reason}',
                status,
                reason,
            )

        try:
            text = response.read().decode('utf-8')
        except IOError as e:
            logger.error(f'error reading GraphQL response: {e}')
            raise GraphQLApiError(
                f'error reading GraphQL response: {e}',
                status,
                reason,
            )

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(json.loads(text))

        response_json = json.loads(text)
        if 'errors' in response_json:
            for error in response_json['errors']:
                logger.error(
                    'GraphQL post error: %s' % error.get('message')
                )

            errs = ','.join([
                error.get('message') for error in response_json['errors']
            ])

            raise GraphQLApiError(
                'GraphQL post error: %s' % errs,
                status,
                reason,
            )


        return response_json['data']


def build_graphql_payload(
    query: str,
    variables: dict = {},
    mutation: bool = False,
) -> dict:
    """Build the GraphQL payload from the given query and variables.

    If `mutation` is True, a mutation query is generated. Otherwise,
    a query is generated.

    :param query: The GraphQL query (or mutation) to run.
    :type query: str
    :param variables: A dictionary of query variables used in the query.
    :type variables: dict
    :param mutation: True if this is a mutation, defaults to False.
    :type mutation: bool, optional
    :return: The GraphQL payload to send, as a dict.
    :rtype: dict
    """

    var_spec = ''
    vars = {}

    for idx, key in enumerate(variables):
        type, value = variables[key]
        if idx > 0:
            var_spec += ','
        var_spec += "$%s: %s" % (key, type)
        vars[key] = value

    if len(vars) > 0:
        var_spec = '(' + var_spec + ')'

    return {
        'query': "%s%s%s" % (
            'mutation' if mutation else 'query',
            var_spec,
            query
        ),
        'variables': vars
    }


def query_graphql(
    api_key: str,
    query: str,
    variables: dict,
    next_cursor_path: str = None,
    mutation: bool = False,
    headers: dict = {},
) -> List[dict]:
    """Make generic GQL queries with built-in pagination support.

    :param api_key: The User API key to use.
    :type api_key: str
    :param query: The GraphQL query (or mutation) to run.
    :type query: str
    :param variables: A dictionary of query variables used in the query.
    :type variables: dict
    :param next_cursor_path: The "path" to a property within a GraphQL
        response that holds the value of the pagination cursor, defaults to
        None.
    :type next_cursor_path: str, optional
    :param mutation: True if this is a mutation, defaults to False.
    :type mutation: bool, optional
    :param headers: Additional headers to send, defaults to {}.
    :type headers: dict, optional
    :raises GraphQLApiError: if the response code of the POST call is not
        a 2XX code or if the `errors` property of the parsed GraphQL
        response is present.
    :raises ApiError: when a next_cursor_path value is specified that is
        invalid.
    :return: A list of result objects, one for each page, will contain a
        single result for unpaged queries.
    :rtype: list[dict]
    """

    done = False
    next_cursor = None
    results = []

    while not done:
        if next_cursor_path:
            variables['cursor'] = ('String', next_cursor)

        gql_result = post_graphql(
            api_key,
            build_graphql_payload(query, variables, mutation),
            headers
        )
        results.append(gql_result)

        if next_cursor_path:
            next_cursor = get_nested(gql_result, next_cursor_path)
            if next_cursor == False:
                raise GraphQLApiError(
                    'expected value at path %s but found none' % next_cursor_path,
                )

        if not next_cursor:
            done = True

    return results


def get_dashboard(api_key: str, guid: str) -> dict:
    """Get the data for a specific dashboard.

    :param api_key: The User API key to use.
    :type api_key: str
    :param guid: The GUID of the dashboard to retrieve.
    :type guid: str
    :return: The dashboard data.
    :rtype: dict
    """

    query = """
{
  actor {
    entity(guid: $guid) {
      ... on DashboardEntity {
        description
        name
        pages {
          description
          guid
          name
          widgets {
            id
            layout {
              column
              height
              row
              width
            }
            linkedEntities {
              guid
            }
            rawConfiguration
            title
            visualization {
              id
            }
          }
        }
        permissions
        variables {
          defaultValues {
            value {
              string
            }
          }
          isMultiSelection
          items {
            title
            value
          }
          name
          nrqlQuery {
            accountIds
            query
          }
          options {
            excluded
            ignoreTimeRange
            showApplyAction
          }
          replacementStrategy
          title
          type
        }
      }
    }
  }
}"""

    variables = {
        'guid': ('EntityGuid!', guid)
    }

    results = query_graphql(api_key, query, variables)
    if len(results) != 1:
        logger.warning(
            'unexpected number of results for dashboard %s: %d',
            guid,
            len(results),
        )
        return

    return results[0]


def update_dashboard(api_key: str, guid: str, dashboard: dict) -> None:
    """Update the data for a specific dashboard.

    :param api_key: The User API key to use.
    :type api_key: str
    :param guid: The GUID of the dashboard to update.
    :type guid: str
    :param dashboard: The updated dashboard data.
    :type dashboard: dict
    :return: None
    """

    query = """
{
  dashboardUpdate(
    dashboard: $dashboard,
    guid: $guid
  ) {
    errors {
      description
      type
    }
  }
}"""

    variables = {
        'guid': ('EntityGuid!', guid),
        'dashboard': ('DashboardInput!', dashboard)
    }

    results = query_graphql(
        api_key,
        query,
        variables,
        mutation=True,
    )

    if len(results) != 1:
        logger.warning(
            'unexpected number of results for dashboard update %s: %d',
            guid,
            len(results),
        )
        return

    errors = get_nested(results, 'dashboardUpdate.errors')
    if errors and len(errors) > 0:
        for error in errors:
            logger.error(
                'failed to update dashboard %s: %s',
                guid,
                error.get('description'),
            )

        errs = ','.join([error.get('description') for error in errors])

        raise GraphQLApiError(
            'failed to update dashboard %s: %s' % (guid, errs),
        )


# -----------------------------------------------------------------------------
# Dashboard processing
# -----------------------------------------------------------------------------


def process_dashboard_entity(
    api_key: str,
    guid: str,
    dashboard: dict,
    refresh_rate: int,
) -> None:
    """Process a single dashboard entity.

    :param api_key: The User API key to use.
    :type api_key: str
    :param guid: The GUID of the dashboard to process.
    :type guid: str
    :param dashboard: The dashboard entity data.
    :type dashboard: dict
    :param refresh_rate: The refresh rate to set for the dashboard.
    :type refresh_rate: int
    :return: None
    """

    entity = get_nested(dashboard, 'actor.entity')
    if not isinstance(entity, dict):
        logger.error(
            "missing or invalid entity definition found for entity %s",
            guid,
        )
        raise DashboardValidationError(
            "missing or invalid entity definition found for entity %s" % guid
        )

    new_dashboard = entity.copy()

    #
    # Get and validate the pages
    #
    pages = new_dashboard.get('pages')
    if not pages:
        logger.info("no pages found for dashboard entity %s", guid)
        return

    if not isinstance(pages, list):
        logger.error(
            "invalid pages found for dashboard entity %s",
            guid,
        )
        raise DashboardValidationError(
            "invalid pages found for dashboard entity %s" % guid
        )

    #
    # Process each page
    #
    for page in new_dashboard['pages']:
        if not isinstance(page, dict):
            logger.error(
                "invalid page definition found for dashboard %s",
                guid,
            )
            raise DashboardValidationError(
                "invalid page definition found for dashboard %s" % guid
            )

        pageGuid = page.get('guid')

        logger.debug(
            'processing page %s for dashboard %s',
            pageGuid,
            guid,
        )

        #
        # Get and validate the widgets
        #
        widgets = page.get('widgets')
        if not widgets:
            logger.info(
                "no widgets found in page %s for dashboard %s",
                pageGuid,
                guid,
            )
            continue

        if not isinstance(widgets, list):
            logger.error(
                'invalid widgets definition found in page %s for dashboard %s',
                pageGuid,
                guid,
            )
            raise DashboardValidationError(
                "invalid widgets definition found in page %s for dashboard %s" % (pageGuid, guid)
            )

        #
        # Process each widget
        #
        for widget in page['widgets']:
            if not isinstance(widget, dict):
                logger.error(
                    'invalid widget definition found in page %s for dashboard %s',
                    pageGuid,
                    guid,
                )
                raise DashboardValidationError(
                    "invalid widget definition found in page %s for dashboard %s" % (pageGuid, guid)
                )

            widgetId = widget.get('id')

            logger.debug(
                'processing widget %s for page %s for dashboard %s',
                widgetId,
                pageGuid,
                guid,
            )

            #
            # Get and validate the linked entities
            #
            linkedEntities = widget.get('linkedEntities')
            if linkedEntities is None:
                logger.info(
                    "no linkedEntities found in widget %s for page %s for dashboard %s",
                    widgetId,
                    pageGuid,
                    guid,
                )
            elif not isinstance(linkedEntities, list):
                logger.error(
                    'invalid linkedEntities found in widget %s for page %s for dashboard %s',
                    widgetId,
                    pageGuid,
                    guid,
                )
                raise DashboardValidationError(
                    "invalid linkedEntities found in widget %s for page %s for dashboard %s" % (widgetId, pageGuid, guid)
                )
            else:
                #
                # Transform the linked entities
                #
                guids = []

                for entity in widget['linkedEntities']:
                    if not isinstance(entity, dict):
                        logger.error(
                            'invalid linked entity found in widget %s for page %s for dashboard %s',
                            widgetId,
                            pageGuid,
                            guid,
                        )
                        raise DashboardValidationError(
                            "invalid linked entity found in widget %s for page %s for dashboard %s" % (widgetId, pageGuid, guid)
                        )

                    if 'guid' in entity:
                        guids.append(entity['guid'])

                widget['linkedEntityGuids'] = guids

            #
            # Remove the linkedEntities field if present
            #
            if 'linkedEntities' in widget:
                del widget['linkedEntities']

            #
            # Get and validate the raw configuration
            #
            rawConfiguration = widget.get('rawConfiguration')
            if rawConfiguration is None:
                logger.info(
                    "no rawConfiguration found in widget %s for page %s for dashboard %s",
                    widgetId,
                    pageGuid,
                    guid,
                )
                rawConfiguration = {}
            elif not isinstance(rawConfiguration, dict):
                logger.error(
                    'invalid rawConfiguration found in widget %s for page %s for dashboard %s',
                    widgetId,
                    pageGuid,
                    guid,
                )
                raise DashboardValidationError(
                    "invalid rawConfiguration found in widget %s for page %s for dashboard %s" % (widgetId, pageGuid, guid)
                )

            if 'refreshRate' in rawConfiguration:
                if not isinstance(rawConfiguration['refreshRate'], dict):
                    logger.error(
                        'invalid refreshRate found in widget %s for page %s for dashboard %s',
                        widgetId,
                        pageGuid,
                        guid,
                    )
                    raise DashboardValidationError(
                        "invalid refreshRate found in widget %s for page %s for dashboard %s" % (widgetId, pageGuid, guid)
                    )

                rawConfiguration['refreshRate']['frequency'] = refresh_rate
            else:
                rawConfiguration['refreshRate'] = {
                    'frequency': refresh_rate
                }

    update_dashboard(api_key, guid, new_dashboard)


def process_dashboard_update(
    api_key: str,
    guid: str,
    refresh_rate: int,
) -> None:
    """Update a single dashboard.

    :param api_key: The User API key to use.
    :type api_key: str
    :param dashboard: The dashboard guid and refresh rate
    :type dashboard: dict
    :return: None
    """

    logger.info(
        'processing dashboard %s with refresh rate %d',
        guid,
        refresh_rate,
    )

    # Get the dashboard entity
    dashboard_entity = get_dashboard(api_key, guid)
    if not dashboard_entity:
        raise DashboardNotFoundError(
            'failed to get dashboard entity for %s' % guid,
        )

    # Process the dashboard entity
    process_dashboard_entity(api_key, guid, dashboard_entity, refresh_rate)

    logger.info(
        'successfully processed dashboard %s with refresh rate %d',
        guid,
        refresh_rate,
    )


def process_dashboard_updates(api_key: str, config: dict) -> None:
    """Update all dashboards in the given config.

    :param api_key: The User API key to use.
    :type api_key: str
    :param config: The configuration.
    :type config: dict
    :return: None
    """

    if not 'dashboards' in config:
        logger.warning('no dashboards found in config')
        return

    if not isinstance(config['dashboards'], list):
        logger.warning('invalid dashboards config: %s', config['dashboards'])
        return

    results = {}

    for dashboard_config in config['dashboards']:
        if not isinstance(dashboard_config, dict):
            logger.warning('invalid dashboard config: %s', dashboard_config)
            continue

        guid = dashboard_config.get('guid')
        refresh_rate = dashboard_config.get('refreshRate')

        if not guid or not refresh_rate:
            logger.warning('invalid dashboard config: %s', dashboard_config)
            continue

        try:
            process_dashboard_update(api_key, guid, refresh_rate)
            results[guid] = 'OK'
        except DashboardNotFoundError as e:
            logger.error(
                f'not found error occurred while processing dashboard %s: {e}',
                guid
            )
            results[guid] = 'NOT FOUND'
        except DashboardValidationError as e:
            logger.error(
                f'validation error occurred while processing dashboard %s: {e}',
                guid
            )
            results[guid] = 'INVALID'
        except GraphQLApiError as e:
            logger.error(
                f'GraphQL API error occurred while processing dashboard %s: {e}',
                guid
            )
            results[guid] = 'API ERROR'

    for guid, status in results.items():
        logger.info(f'{guid}: {status}')


# -----------------------------------------------------------------------------
# Main entry point
# -----------------------------------------------------------------------------

def main():
    '''Main entry point for the script.
    :return: None
    '''

    logger.info(f'starting with program arguments {sys.argv[1:]}')

    try:
        # Parse command line arguments
        options = parse_args()

        # Check for debug logging
        if options.debug:
            logger.setLevel(logging.DEBUG)

        # Load config
        config = load_config(options.config_file)

        # Get API key from config or environment variable
        api_key = config.get('api_key') or os.getenv('NEW_RELIC_API_KEY')
        if not api_key:
            logger.error('no API key found!')
            sys.exit(1)

        # Process dashboards
        process_dashboard_updates(api_key, config)

    except Exception as e:
        logger.error(f'error occurred: {e}')
        traceback.print_exception(e)
        sys.exit(1)

    finally:
        logger.info('finished')

if __name__ == "__main__":
    main()

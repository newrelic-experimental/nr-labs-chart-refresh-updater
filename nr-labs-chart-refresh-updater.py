# Standard library imports
import datetime
import logging
import json
import optparse
import os
import sys
import traceback
from typing import Callable, List, Any
from urllib.request import Request, urlopen, HTTPError


# Setup logging to stdout with a decent format
logging.basicConfig(
    format='%(asctime)s - %(levelname)s: %(message)s',
    stream=sys.stdout,
    level=logging.INFO
)


# Create the global logger
logger = logging.getLogger(__name__)


# The GraphQL endpoints
GRAPHQL_US_URL = 'https://api.newrelic.com/graphql'
GRAPHQL_EU_URL = 'https://api.eu.newrelic.com/graphql'


# The default configuration file name
# NOTE: We use JSON instead of YML because YML support is not part of the
# Python standard library and we want this script to be dependency-free.
DEFAULT_CONFIG_FILE = 'config.json'


# The backup file name datetime format
BACKUP_FILE_NAME_DATETIME_FORMAT = '%Y%m%d_%H%M%S'


# -----------------------------------------------------------------------------
# Error classes
# -----------------------------------------------------------------------------


class GraphQLApiError(Exception):
    """Exception raised for GraphQL errors.
    """

    def __init__(
        self,
        message: str,
        status: int,
        reason: str
    ):
        """The constructor method.

        :param message: A message describing the error that occurred.
        :type message: str
        :param status: The HTTP status code returned on the API call.
        :type status: int
        :param reason: The HTTP reason returned on the API call.
        :type reason: str
        """

        super().__init__(message)
        self.status = status
        self.reason = reason


class DashboardNotFoundError(Exception):
    """Exception raised for dashboard not found errors.
    """

    def __init__(
        self,
        message: str,
    ):
        """The constructor method.

        :param message: A message describing the error that occurred.
        :type message: str
        """

        super().__init__(message)


class DashboardValidationError(Exception):
    """Exception raised for dashboard validation errors.
    """

    def __init__(
        self,
        message: str,
    ):
        """The constructor method.

        :param message: A message describing the error that occurred.
        :type message: str
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


def get_backup_name(guid: str) -> str:
    """Generate a backup file name for the given dashboard GUID.

    :returns: A backup file name for the given dashboard GUID.
    :rtype: str
    """

    now = datetime.datetime.now(datetime.timezone.utc)
    now_str = now.strftime(BACKUP_FILE_NAME_DATETIME_FORMAT)

    return f"dashboard_{guid}_{now_str}.json"


# -----------------------------------------------------------------------------
# I/O functions
# -----------------------------------------------------------------------------


def backup_dashboard(
    backup_dir: str,
    guid: str,
    dashboard: dict,
) -> None:
    """Create a backup copy of the given dashboard definition.

    :param backup_dir: The directory to save the backup file in.
    :type backup_dir: str
    :param guid: The GUID of the dashboard to back up.
    :type guid: str
    :param dashboard: The dashboard definition to back up.
    :type dashboard: dict
    :returns: None
    :rtype: None
    """

    os.makedirs(backup_dir, exist_ok=True)

    backup_path = os.path.join(backup_dir, get_backup_name(guid))

    with open(backup_path, 'w') as backup_file:
        logger.debug(f'Creating backup for dashboard {guid} at {backup_path}')
        json.dump(dashboard, backup_file, indent=2)
        logger.debug(
            f'Backup for dashboard {guid} created successfully at {backup_path}',
        )


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
        '--backup-dir',
        default=None,
        help='directory to save backup files',
    )

    parser.add_option(
        '--no-backup',
        action='store_true',
        help='disable backup creation',
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
    :returns: The loaded configuration as a dictionary.
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
    :returns: A dictionary containing HTTP headers for a Nerdgraph call.
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
    region: str = 'US'
) -> dict:
    """Make the actual GraphQL POST call using the given payload.

    :param api_key: The User API key to use.
    :type api_key: str
    :param payload: The payload to send, as a dict.
    :type payload: dict
    :param headers: Additional headers to send, defaults to {}.
    :type headers: dict, optional
    :param region: The region to use for the GraphQL API call, defaults to 'US'.
    :type region: str, optional
    :raises GraphQLApiError: if the response code of the POST call is not
        a 2XX code or if an HTTPError is raised or if the `errors` property of
        the parsed GraphQL response is present.
    :returns: The `data` property of the parsed GraphQL response as a dict.
    :rtype: dict
    """

    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(json.dumps(payload, indent=2))

    request = Request(
        GRAPHQL_EU_URL if region == 'EU' else GRAPHQL_US_URL,
        data=json.dumps(payload).encode('utf-8'),
        headers=build_graphql_headers(api_key, headers),
    )

    try:
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
            except OSError as e:
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
    except HTTPError as e:
        logger.error(
            f'HTTP error occurred with status: {e.code}, reason: {e.reason}',
        )
        raise GraphQLApiError(
            f'HTTP error occurred with status: {e.code}, reason: {e.reason}',
            e.code,
            e.reason,
        )


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
    :returns: The GraphQL payload to send, as a dict.
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
    region: str = 'US',
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
    :param region: The region to use for the GraphQL API call, defaults to 'US'.
    :type region: str, optional
    :raises GraphQLApiError: if the response code of the GraphQL API call is not
        a 2XX code or if an HTTPError is raised or if the `errors` property of
        the parsed GraphQL response is present.
    :returns: A list of result objects, one for each page. Contains a single
        result for unpaged queries.
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
            headers,
            region,
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


def get_dashboard(api_key: str, guid: str, region: str = 'US') -> dict:
    """Get the dashboard definition for the specified dashboard entity.

    :param api_key: The User API key to use.
    :type api_key: str
    :param guid: The GUID of the dashboard entity to retrieve.
    :type guid: str
    :param region: The region to use for the GraphQL API call, defaults to 'US'.
    :type region: str, optional
    :raises GraphQLApiError: if the response code of the GraphQL API call is not
        a 2XX code or if an HTTPError is raised or if the `errors` property of
        the parsed GraphQL response is present or if more or less than one
        result is found or if the dashboard definition is not valid.
    :returns: The dashboard definition for the specified dashboard entity.
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

    results = query_graphql(api_key, query, variables, region=region)
    if len(results) != 1:
        logger.error(
            'unexpected number of results for dashboard entity %s: %d',
            guid,
            len(results),
        )
        raise GraphQLApiError(
            'unexpected number of results for dashboard entity %s: %d' % \
                (guid, len(results))
        )

    # Get the dashboard definition
    dashboard = get_nested(results[0], 'actor.entity')
    if not isinstance(dashboard, dict):
        logger.error(
            'missing or invalid dashboard definition found for dashboard entity %s',
            guid,
        )
        raise GraphQLApiError(
            'missing or invalid dashboard definition found for dashboard entity %s' \
                % guid
        )

    return dashboard


def update_dashboard(
    api_key: str,
    guid: str,
    dashboard: dict,
    region: str = 'US',
) -> None:
    """Update the definition for specified dashboard entity.

    :param api_key: The User API key to use.
    :type api_key: str
    :param guid: The GUID of the dashboard entity to update.
    :type guid: str
    :param dashboard: The updated dashboard definition.
    :type dashboard: dict
    :param region: The region to use for the GraphQL API call, defaults to 'US'.
    :type region: str, optional
    :raises GraphQLApiError: if the response code of the GraphQL API call is not
        a 2XX code or if an HTTPError is raised or if the `errors` property of
        the parsed GraphQL response is present or if more or less than one
        result is found or if the `errors` property of the `dashboardUpdate`
        response is present.
    :returns: None
    :rtype: None
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
        region=region,
    )

    if len(results) != 1:
        logger.warning(
            'unexpected number of results for update to dashboard entity %s: %d',
            guid,
            len(results),
        )
        raise GraphQLApiError(
            'unexpected number of results for update to dashboard entity %s: %d' \
                % (guid, len(results))
        )

    errors = get_nested(results, 'dashboardUpdate.errors')
    if errors and len(errors) > 0:
        for error in errors:
            logger.error(
                'failed to update dashboard entity %s: %s',
                guid,
                error.get('description'),
            )

        errs = ','.join([error.get('description') for error in errors])

        raise GraphQLApiError(
            'failed to update dashboard entity %s: %s' % (guid, errs),
        )


# -----------------------------------------------------------------------------
# Dashboard processing
# -----------------------------------------------------------------------------


def transform_widgets(
    guid: str,
    dashboard: dict,
    transformerFn: Callable[[dict], None]
) -> None:
    """Visit each widget in the dashboard and apply the given transformation
    function.

    :param guid: The GUID of the dashboard entity.
    :type guid: str
    :param dashboard: The dashboard definition.
    :type dashboard: dict
    :raises DashboardValidationError: if the page or widget definitions are
    invalid.
    :returns: None
    :rtype: None
    """

    #
    # Get and validate the pages
    #
    pages = dashboard.get('pages')
    if not pages:
        logger.debug("no pages found for dashboard entity %s", guid)
        return

    if not isinstance(pages, list):
        logger.error(
            "invalid pages element found for dashboard entity %s",
            guid,
        )
        raise DashboardValidationError(
            "invalid pages element found for dashboard entity %s" % guid
        )

    #
    # Process each page
    #
    for page in dashboard['pages']:
        if not isinstance(page, dict):
            logger.error(
                "invalid page definition found for dashboard entity %s",
                guid,
            )
            raise DashboardValidationError(
                "invalid page definition found for dashboard entity %s" % guid
            )

        pageGuid = page.get('guid')

        logger.debug(
            'processing page %s for dashboard entity %s',
            pageGuid,
            guid,
        )

        #
        # Get and validate the widgets
        #
        widgets = page.get('widgets')
        if not widgets:
            logger.debug(
                "no widgets found in page %s for dashboard entity %s",
                pageGuid,
                guid,
            )
            continue

        if not isinstance(widgets, list):
            logger.error(
                'invalid widgets element found in page %s for dashboard entity %s',
                pageGuid,
                guid,
            )
            raise DashboardValidationError(
                "invalid widgets element found in page %s for dashboard entity %s" \
                    % (pageGuid, guid)
            )

        #
        # Process each widget
        #
        for widget in page['widgets']:
            if not isinstance(widget, dict):
                logger.error(
                    'invalid widget definition found in page %s for dashboard entity %s',
                    pageGuid,
                    guid,
                )
                raise DashboardValidationError(
                    "invalid widget definition found in page %s for dashboard entity %s" \
                        % (pageGuid, guid)
                )

            widgetId = widget.get('id')

            logger.debug(
                'transforming widget %s for page %s for dashboard entity %s',
                widgetId,
                pageGuid,
                guid,
            )

            transformerFn(guid, pageGuid, widgetId, widget)


def transform_linked_entities(
    guid: str,
    pageGuid: str,
    widgetId: str,
    widget: dict,
) -> None:
    """Transform the linkedEntities field to linkedEntityGuids for the specified
    widget.

    :param guid: The GUID of the dashboard entity.
    :type guid: str
    :param pageGuid: The GUID of the page.
    :type pageGuid: str
    :param widgetId: The ID of the widget.
    :type widgetId: str
    :param widget: The widget to transform.
    :type widget: dict
    :raises DashboardValidationError: if the linkedEntities definition is invalid.
    :returns: None
    :rtype: None
    """

    linkedEntities = widget.get('linkedEntities')
    if linkedEntities is None:
        logger.debug(
            "no linkedEntities found in widget %s for page %s for dashboard entity %s",
            widgetId,
            pageGuid,
            guid,
        )
    elif not isinstance(linkedEntities, list):
        logger.error(
            'invalid linkedEntities element found in widget %s for page %s for dashboard entity %s',
            widgetId,
            pageGuid,
            guid,
        )
        raise DashboardValidationError(
            "invalid linkedEntities element found in widget %s for page %s for dashboard entity %s" \
                % (widgetId, pageGuid, guid)
        )
    else:
        # Build the linkedEntityGuids element from the list of linkedEntities

        guids = []

        for entity in linkedEntities:
            if not isinstance(entity, dict):
                logger.error(
                    'invalid linked entity element found in widget %s for page %s for dashboard entity %s',
                    widgetId,
                    pageGuid,
                    guid,
                )
                raise DashboardValidationError(
                    "invalid linked entity element found in widget %s for page %s for dashboard entity %s" \
                        % (widgetId, pageGuid, guid)
                )

            if 'guid' in entity:
                guids.append(entity['guid'])

        widget['linkedEntityGuids'] = guids

    # Remove the original linkedEntities field if present
    if 'linkedEntities' in widget:
        del widget['linkedEntities']


def fixup_linked_entities(
    guid: str,
    dashboard: dict,
) -> None:
    """Fixup any linkedEntities fields found in the widgets in the specified
    dashboard.

    :param guid: The GUID of the dashboard entity .
    :type guid: str
    :param dashboard: The dashboard definition.
    :type dashboard: dict
    :raises DashboardValidationError: if validation issues are encountered while
    transforming the dashboard definition.
    :returns: None
    :rtype: None
    """

    logger.debug(f'fixing up linked entities for dashboard entity %s', guid)

    transform_widgets(
        guid,
        dashboard,
        transform_linked_entities,
    )


def update_refresh_rate(
    guid: str,
    pageGuid: str,
    widgetId: str,
    widget: dict,
    refresh_rate: int,
) -> None:
    """Update the refresh rate for the specified widget.

    :param guid: The GUID of the dashboard entity.
    :type guid: str
    :param pageGuid: The GUID of the page.
    :type pageGuid: str
    :param widgetId: The ID of the widget.
    :type widgetId: str
    :param widget: The widget to update.
    :type widget: dict
    :param refresh_rate: The new refresh rate.
    :type refresh_rate: int
    :raises DashboardValidationError: if the rawConfiguration or refreshRate
    definitions are invalid.
    :returns: None
    :rtype: None
    """

    # Get and validate the raw configuration
    rawConfiguration = widget.get('rawConfiguration')
    if rawConfiguration is None:
        logger.info(
            "no rawConfiguration element found in widget %s for page %s for dashboard entity %s",
            widgetId,
            pageGuid,
            guid,
        )
        rawConfiguration = {}
    elif not isinstance(rawConfiguration, dict):
        logger.error(
            'invalid rawConfiguration element found in widget %s for page %s for dashboard entity %s',
            widgetId,
            pageGuid,
            guid,
        )
        raise DashboardValidationError(
            "invalid rawConfiguration element found in widget %s for page %s for dashboard entity %s" \
                % (widgetId, pageGuid, guid)
        )

    if 'refreshRate' in rawConfiguration:
        if not isinstance(rawConfiguration['refreshRate'], dict):
            logger.error(
                'invalid refreshRate element found in widget %s for page %s for dashboard entity %s',
                widgetId,
                pageGuid,
                guid,
            )
            raise DashboardValidationError(
                "invalid refreshRate element found in widget %s for page %s for dashboard entity %s" \
                    % (widgetId, pageGuid, guid)
            )

        rawConfiguration['refreshRate']['frequency'] = refresh_rate
    else:
        rawConfiguration['refreshRate'] = { 'frequency': refresh_rate }


def update_refresh_rates(
    guid: str,
    dashboard: dict,
    refresh_rate: int,
) -> None:
    """Update all refresh rates for the widgets in the specified dashboard.

    :param guid: The GUID of the dashboard entity.
    :type guid: str
    :param dashboard: The dashboard definition.
    :type dashboard: dict
    :param refresh_rate: The refresh rate to set for the widgets in the dashboard.
    :type refresh_rate: int
    :raises DashboardValidationError: if validation issues are encountered while
    transforming the dashboard definition.
    :returns: None
    :rtype: None
    """

    def transformer(
        guid: str,
        pageGuid: str,
        widgetId: str,
        widget: dict,
    ) -> None:
        update_refresh_rate(
            guid,
            pageGuid,
            widgetId,
            widget,
            refresh_rate
        )

    logger.debug(f'updating refresh rates for dashboard entity %s', guid)

    transform_widgets(
        guid,
        dashboard,
        transformer,
    )


def process_dashboard_update(
    api_key: str,
    guid: str,
    refresh_rate: int,
    backup_dir: str,
    region: str = 'US',
) -> None:
    """Update a single dashboard.

    :param api_key: The User API key to use.
    :type api_key: str
    :param guid: The GUID of the dashboard entity.
    :type guid: str
    :param refresh_rate: The refresh rate in milliseconds.
    :type refresh_rate: int
    :param backup_dir: The directory where the backup file should be stored. If
    None is specified, no backup will be created.
    :type backup_dir: str
    :param region: The region to use for GraphQL API calls, defaults to 'US'.
    :type region: str, optional
    :returns: None
    :rtype: None
    """

    logger.info(
        'processing dashboard entity %s with refresh rate %d',
        guid,
        refresh_rate,
    )

    # Get the dashboard definition
    dashboard = get_dashboard(api_key, guid, region)

    # Fixup the linkedEntities field in the widgets
    fixup_linked_entities(guid, dashboard)

    # Backup the original dashboard definition before changes are made.
    if backup_dir:
        backup_dashboard(backup_dir, guid, dashboard)

    # Update the refresh rates
    update_refresh_rates(guid, dashboard, refresh_rate)

    # Update the dashboard entity with the new dashboard definition
    update_dashboard(api_key, guid, dashboard, region)

    logger.info(
        'successfully processed dashboard entity %s with refresh rate %d',
        guid,
        refresh_rate,
    )


def process_dashboard_updates(
    api_key: str,
    config: dict,
    backup_dir: str,
    region: str = 'US',
) -> None:
    """Update all dashboards in the given config.

    :param api_key: The User API key to use.
    :type api_key: str
    :param config: The user configuration.
    :type config: dict
    :param backup_dir: The directory where backup files should be stored. If
    None is specified, no backups will be created.
    :type backup_dir: str
    :param region: The region to use for GraphQL API calls, defaults to 'US'.
    :type region: str, optional
    :returns: None
    :rtype: None
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
            process_dashboard_update(
                api_key,
                guid,
                refresh_rate,
                backup_dir,
                region,
            )
            results[guid] = 'OK'
        except DashboardNotFoundError as e:
            logger.error(
                f'not found error occurred while processing dashboard entity %s: {e}',
                guid
            )
            results[guid] = 'NOT FOUND'
        except DashboardValidationError as e:
            logger.error(
                f'validation error occurred while processing dashboard entity %s: {e}',
                guid
            )
            results[guid] = 'INVALID'
        except GraphQLApiError as e:
            logger.error(
                f'GraphQL API error occurred while processing dashboard entity %s: {e}',
                guid
            )
            results[guid] = 'API ERROR'

    for guid, status in results.items():
        logger.info(f'{guid}: {status}')


# -----------------------------------------------------------------------------
# Main entry point
# -----------------------------------------------------------------------------


def main() -> None:
    '''Main entry point for the script.

    :returns: None
    :rtype: None
    '''

    logger.info(f'starting with program arguments {sys.argv[1:]}')

    try:
        # Parse command line arguments
        options = parse_args()

        # Maybe enable debug logging
        if options.debug:
            logger.setLevel(logging.DEBUG)

        # Load config
        config = load_config(options.config_file)

        # Get API key from config or environment variable
        api_key = config.get('apiKey') or os.getenv('NEW_RELIC_API_KEY')
        if not api_key:
            logger.error('no API key found!')
            sys.exit(1)

        # Get region from config or environment variable, otherwise default to
        # US
        region = config.get('region') or os.getenv('NEW_RELIC_REGION') or 'US'

        # Resolve the backup directory
        backup_dir = None

        if not options.no_backup:
            # Get the backup directory from the command line options or config,
            # otherwise use the current working directory
            backup_dir = options.backup_dir or \
                config.get('backupDir') or \
                os.getcwd()

        # Process dashboards
        process_dashboard_updates(api_key, config, backup_dir, region)

    except Exception as e:
        logger.error(f'unexpected error occurred: {e}')
        traceback.print_exception(e)
        sys.exit(1)

    finally:
        logger.info('finished')


if __name__ == "__main__":
    main()

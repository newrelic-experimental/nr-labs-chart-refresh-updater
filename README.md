# nr-labs-chart-refresh-updater

Perform bulk updates of chart refresh rates.

## Introduction

This repository contains a single file, dependency-free Python script that can
be used to perform bulk changes to refresh rates on New Relic dashboards.

## System Requirements

- Python 3.12 or newer

## Getting Started

**NOTE:** Please read the warning message in the ["Backup Files"](#backup-files)
section of this document prior to getting started.

1. Clone this repository

   ```sh
   git clone git@github.com:newrelic-experimental/nr-labs-chart-refresh-updater.git
   ```

1. Navigate to the repository root directory

   ```sh
   cd nr-labs-chart-refresh-updater
   ```

1. Copy the sample configuration file

   ```sh
   cp config_sample.json config.json
   ```

1. Edit the sample configuration as follows:

   1. Set the `apiKey` value to your New Relic [User key](https://docs.newrelic.com/docs/apis/intro-apis/new-relic-api-keys/#user-key)
   1. Set the `region` value to `US` or `EU` as appropriate for your account
   1. Set the `backupDir` value to a path to a directory on the local file
      system where backups should be created (**NOTE:** Relative paths will be
      resolved relative to the current working directory at the time the updater
      is run.)
   1. For each dashboard to update, add an object to the `dashboards` array with
      the following format:

      ```json
      {
        "guid": "DASHBOARD_GUID",
        "refreshRate": 5000
      }
      ```

      Replace `DASHBOARD_GUID` with the unique entity GUID of the dashboard to
      update and set the value for the `refreshRate` property to the refresh
      rate, in *milliseconds*, to be applied to all charts on all pages of the
      dashboard.

1. Run the updater as follows:

   ```sh
   python3 nr-labs-chart-refresh-updater.py
   ```

## Usage

* [Installation](#installation)
* [Configuration](#configuration)
* [Using the CLI](#using-the-cli)
* [Backup Files](#backup_files)

### Installation

The updater script is a single file, dependency-free Python script that requires
no specific installation steps. Simply copy the script to the system where it
should be run and use a supported Python version to run the script.

### Configuration

The updater is configured using a JSON file. By default, the updater will
attempt to load the file named `config.json` from the current working directory
at the time the updater is run. The `-f` command line option can be used to
specify a different configuration file to load.

The supported configuration parameters are documented below.

#### `apiKey`

Use this configuration parameter to specify your New Relic [User key](https://docs.newrelic.com/docs/apis/intro-apis/new-relic-api-keys/#user-key).
This value can also be specified using the environment variable named
`NEW_RELIC_API_KEY`. The environment variable takes precedence.

#### `region`

Use this configuration parameter to specify the New Relic [data center](https://docs.newrelic.com/docs/accounts/accounts-billing/account-setup/choose-your-data-center/)
where your account data is stored. This value can also be specified using the
environment variable named `NEW_RELIC_REGION`. Valid values are `US` and `EU`
(case sensitive).

#### `backupDir`

Use this configuration parameter to specify the directory where backup files
should be stored. By default, the updater will store backup files in the current
working directory at the time the updater is run. The `--backup-dir` [command line option can](#using-the-cli)
be used to specify a different backup directory. Backup creation can be disabled
using the [command line option](#using-the-cli) `--no-backup`.

#### `dashboards`

Use this configuration parameter to specify the dashboards to be updated and the
refresh rate for each dashboard. Each element of this list should have the
following format.

```json
{
   "guid": "A_DASHBOARD_GUID",
   "refreshRate": 5000
}
```

Replace `DASHBOARD_GUID` with the unique entity GUID of the dashboard to update
and set the value for the `refreshRate` property to the refresh rate, in
*milliseconds*, to be applied to all charts on all pages of the dashboard.

### Using the CLI

The updater script supports the following command line options.

| Option | Description | Default |
| --- | --- | --- |
| `-f`, `--config_file` | path to the configuration file to use | `config.json` |
| `--backup-dir` | path to a directory on the local file system where backup files should be stored | current working directory |
| `--no-backup` | flag to disable backup creation | `false` |
| `-d`, `--debug` | flag to enable "debug" mode | `false` |

**NOTES:**
* Relative paths specified for the `-f`/`--config-file` and `--backup-dir`
  options will be resolved relative to the current working directory at the time
  the updater is run.

### Backup Files

The updater script will automatically store backups of each dashboard definition
prior to updating the refresh rates. These files can be used to restore the
dashboards to their previous state prior to alterations made by the updater.

Backup files are created with the following naming scheme.

`dashboard_[GUID]_[YYYYmmdd_HHMMSS.json]`

For example, for the dashboard with GUID `12345` backed up on October 13th, 2025
at 10:30:00 UTC, the filename would be as follows.

`dashboard_12345_20251013_103000.json`.

The time is always in the UTC timezone.

To restore a dashboard to it's previous state using a backup file, follow the
directions to [manage the dashboard JSON](https://docs.newrelic.com/docs/query-your-data/explore-query-data/dashboards/manage-your-dashboard/#manage-json)
for the desired dashboard, copy and paste the contents of the backup file into
the JSON text field, and click on the button labeled "Save changes".

**WARNING:** Backup files are created using the dashboard definition schema that
is current as of 10/13/2025. It is possible for this schema to change in the
future at which time the backup dashboard definitions created by the updater
script may not capture all the information needed to properly recreate a
dashboard. For this reason, it is recommended to manually download the current
JSON of the desired dashboards as a backup, using the button labeled "Download"
from the ["Manage JSON"](https://docs.newrelic.com/docs/query-your-data/explore-query-data/dashboards/manage-your-dashboard/#manage-json)
dialog prior to using the updater script to make alterations to the desired
dashboards.

## Support

New Relic has open-sourced this project. This project is provided AS-IS WITHOUT
WARRANTY OR DEDICATED SUPPORT. Issues and contributions should be reported to
the project here on GitHub.

We encourage you to bring your experiences and questions to the
[Explorers Hub](https://discuss.newrelic.com/) where our community members
collaborate on solutions and new ideas.

### Privacy

At New Relic we take your privacy and the security of your information
seriously, and are committed to protecting your information. We must emphasize
the importance of not sharing personal data in public forums, and ask all users
to scrub logs and diagnostic information for sensitive information, whether
personal, proprietary, or otherwise.

We define “Personal Data” as any information relating to an identified or
identifiable individual, including, for example, your name, phone number, post
code or zip code, Device ID, IP address, and email address.

For more information, review [New Relic’s General Data Privacy Notice](https://newrelic.com/termsandconditions/privacy).

### Contribute

We encourage your contributions to improve this project! Keep in mind that
when you submit your pull request, you'll need to sign the CLA via the
click-through using CLA-Assistant. You only have to sign the CLA one time per
project.

If you have any questions, or to execute our corporate CLA (which is required
if your contribution is on behalf of a company), drop us an email at
opensource@newrelic.com.

**A note about vulnerabilities**

As noted in our [security policy](../../security/policy), New Relic is committed
to the privacy and security of our customers and their data. We believe that
providing coordinated disclosure by security researchers and engaging with the
security community are important means to achieve our security goals.

If you believe you have found a security vulnerability in this project or any of
New Relic's products or websites, we welcome and greatly appreciate you
reporting it to New Relic through [HackerOne](https://hackerone.com/newrelic).

If you would like to contribute to this project, review [these guidelines](./CONTRIBUTING.md).

To all contributors, we thank you!  Without your contribution, this project
would not be what it is today.

### License

The [New Relic Salesforce Exporter] project is licensed under the
[Apache 2.0](http://apache.org/licenses/LICENSE-2.0.txt) License.

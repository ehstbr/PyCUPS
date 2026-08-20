# Security policy

## Supported versions

The newest PyCUPS release receives security fixes. Upgrade before reporting a
problem so the result reflects the current code.

| Version | Supported |
| --- | --- |
| 0.1.14 | Yes |
| Older releases | No |

## Reporting a vulnerability

Use GitHub's private
[security advisory form](https://github.com/ehstbr/PyCUPS/security/advisories/new).
Do not open a public issue with exploit details, credentials, retained print
documents, spool data, usernames, addresses, or printer/network information.

Include the PyCUPS version, Linux distribution, CUPS version, impact, and the
smallest sanitized reproduction you can provide. If private vulnerability
reporting is unavailable, open a public issue only to request a private contact
channel—do not include vulnerability details there.

## Security boundaries

PyCUPS never needs direct access to `/var/spool/cups`. It retrieves retained
documents through authorized CUPS operations and limits privileged changes to
the packaged PolicyKit helper. Installing or opening the application must not
alter CUPS configuration.

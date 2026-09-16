"""Stable, version-independent discovery URLs. Nothing else lives here —
no version strings, no CDN URLs. See spec §6.
"""

SOURCES = {
    "jira-platform": {
        "discovery_url": "https://developer.atlassian.com/cloud/jira/platform/rest/",
    },
    "jira-software": {
        "discovery_url": "https://developer.atlassian.com/cloud/jira/software/rest/",
    },
    "confluence": {
        "discovery_url": "https://developer.atlassian.com/cloud/confluence/rest/",
    },
}

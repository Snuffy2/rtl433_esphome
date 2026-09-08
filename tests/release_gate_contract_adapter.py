"""Repository-specific release gate identities for shared contract tests."""

GATES = (
    {
        "workflow": "validation.yml",
        "job": "validation",
        "product": "firmware",
        "required_check": "validation.yml::Test and build",
    },
    {
        "workflow": "prek-autofix-review.yml",
        "job": "review",
        "product": "prek",
        "required_check": "prek-autofix-review.yml::review",
    },
)

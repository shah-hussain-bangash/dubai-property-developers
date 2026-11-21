# GitHub workflow validation

The `workflow-lint` job in [CI](../../.github/workflows/ci.yml) checks every GitHub workflow with Actionlint 1.7.12. Its Linux archive is downloaded from the official release and verified against a fixed SHA-256 digest before execution. ShellCheck must be available so shell steps are also checked.

The validator checks YAML structure, action inputs, expressions and context availability, matrix references and job dependencies. It runs alongside the existing tests, audits, credential scan and container checks.

## Before pushing a workflow change

Use the official [Actionlint release](https://github.com/rhysd/actionlint/releases/tag/v1.7.12), verify the archive checksum, and run this command from the repository root:

```text
actionlint
```

With explicit file paths, for example:

```text
actionlint .github/workflows/ci.yml .github/workflows/dependency-review.yml
```

Install ShellCheck for the shell-step checks; CI requires it. A local Windows run without ShellCheck still validates workflow syntax and expressions.

Run local validation before pushing. GitHub may be unable to start a workflow containing an invalid expression context, so CI alone cannot validate every broken workflow. For example, `runner.temp` is unavailable inside job-level `env`; shell steps can use `$RUNNER_TEMP` after a runner has started.

## Updating the tool

Update the pinned release URL and Linux archive SHA-256 together after verifying the official release. Check existing workflows locally, then review the `workflow-lint` job and the remaining CI results before merging.

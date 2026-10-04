# Security and Privacy

## Public Repository Policy

This repository is a sanitized portfolio snapshot, not a production mirror.

## Intentionally Excluded

The public tree excludes:

- `.env` and production environment files;
- API keys, access tokens, private keys, and credentials;
- citizen production records and uploaded citizen documents;
- production SQLite or external database contents;
- production cookies or sessions;
- private infrastructure identifiers;
- internal audit evidence;
- hidden / held-out acceptance datasets;
- internal qualification and canary datasets;
- production deployment workflows.

## Included Configuration

`backend/.env.example` contains environment-variable names and safe development defaults/placeholders only.

Real secrets should be stored in an untracked local `.env` or an appropriate secret manager.

## Sensitive Citizen Data

The application architecture includes privacy-oriented request handling. The public repository does not include real NIK, KK numbers, citizen chat logs, addresses, phone numbers, or production documents.

## Deployment Boundary

This repository has no automatic connection to the production Railway deployment. Publishing or pushing this repository must not deploy the production system.

## Reporting a Security Issue

Please avoid opening a public issue containing a credential, personal record, or exploit payload. Contact the repository owner privately through their professional contact channel instead.

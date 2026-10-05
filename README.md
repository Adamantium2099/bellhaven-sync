# Bellhaven CRM Reconciliation

A human-in-the-loop reconciliation system for keeping Bellhaven Senior Living's CRM facility ownership records aligned with its current public website.

The pipeline scrapes Bellhaven's current locations, retrieves CRM accounts through the provided API, matches facilities using auditable identity evidence, proposes corrections, and requires human approval before any CRM write occurs.

## Why This Exists

Accurate parent ownership relationships matter for sales and account management, but CRM data can contain stale names, incorrect parents, duplicates, historical ownership records, and facilities that have not yet been created.

This project separates two questions:

1. Does a website facility correspond to a particular CRM account?
2. If it does, what CRM action is safe given the account's ownership and financial history?

That separation is important because a strong location match does not necessarily mean an account can safely be re-parented.

## Architecture

```text
Bellhaven website
        |
        v
    scraper.py
        |
        v
website facility snapshot
        |
        +-------------------+
                            |
CRM API                     |
  |                         |
  v                         v
crm_client.py ----------> matcher.py
                            |
                            v
                   reconciliation proposals
                            |
                            v
                       app.py
                  human review/approval
                            |
                            v
                       executor.py
                            |
                            v
                         CRM API
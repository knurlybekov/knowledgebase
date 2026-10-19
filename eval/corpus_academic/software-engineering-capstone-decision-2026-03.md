# Capstone project: framework decision (March 2026)

## Problem
The capstone team needed a backend framework for the emergency plan editor. The first prototype in Flask had grown three different ways to validate input and no migrations, and the supervisor asked for a decision before the April milestone.

## Options
The team compared Flask with SQLAlchemy and Alembic, Django with the Django REST Framework, and FastAPI with SQLModel. FastAPI was the fastest to prototype. Django brought migrations, an admin site, and an authentication system the team would otherwise write.

## Decision
On 2026-03-12 the team selected Django with the Django REST Framework. The deciding factors were built-in migrations, the admin site for the client's reviewers, and the supervisor's familiarity with the framework.

## Rationale
The team estimated two weeks saved on authentication and admin screens. FastAPI's speed advantage did not matter at the expected load of forty concurrent users.

## Change
On 2026-04-20 the team moved the background jobs from Django's synchronous views to Celery with Redis after the PDF export blocked requests for up to twenty seconds. The framework decision itself did not change.

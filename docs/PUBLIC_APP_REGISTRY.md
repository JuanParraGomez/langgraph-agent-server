# Public App Registry Usage

The UI factory graph treats `hapi` as the public app registry.

Lookup order:
1. `GET /public/apps/by-slug/{slug}`
2. `GET /public/apps/by-domain/{domain}` if domain is known

Write order:
1. `POST /public/apps/register`
2. `POST /public/apps/{app_id}/deployment`
3. `POST /public/apps/{app_id}/sync`

This prevents LangGraph from guessing public state from Git or Coolify alone.

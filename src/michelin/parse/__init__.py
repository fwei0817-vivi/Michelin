"""Stage 1: menu photos -> data/menus/<slug>.json. Owned by the LLM teammate.

Only requirement from the rest of the team: the output validates as `michelin.schemas.Menu`
and a human sets `verified: true` before the file is used by the API.
"""

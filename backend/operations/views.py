"""Compatibility facade. Business logic is separated into process_1 and process_2."""
from process_1.views import *  # noqa: F401,F403
from process_2.views import reconciliation, recon_action  # noqa: F401

"""Authority matrix and conversation rules: who may send which message, to whom, and when
(doc 05 §15). Pure and deterministic; the rules are data (config/protocol/authority.toml)."""

from netcoop.core.guard.guard import DEPRECATED_CODE_ALIASES as DEPRECATED_CODE_ALIASES
from netcoop.core.guard.guard import ConversationGuard as ConversationGuard
from netcoop.core.guard.guard import GuardResult as GuardResult
from netcoop.core.guard.guard import Violation as Violation
from netcoop.core.guard.rules import AUTHORITY_PATH as AUTHORITY_PATH
from netcoop.core.guard.rules import AuthorityRow as AuthorityRow
from netcoop.core.guard.rules import AuthorityRules as AuthorityRules
from netcoop.core.guard.rules import load_rules as load_rules
from netcoop.core.guard.state import ConversationState as ConversationState
from netcoop.core.guard.state import OpenRequest as OpenRequest
from netcoop.core.guard.state import rebuild_state as rebuild_state

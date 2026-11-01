"""Protocol inspector: pure functions that turn an incident's message log into readable text
or structured data (doc 05 §18). Nothing here prints; the CLI (netcoop.cli.trace) does."""

from netcoop.core.inspector.render import BANNER_TEXT as BANNER_TEXT
from netcoop.core.inspector.render import TraceView as TraceView
from netcoop.core.inspector.render import evidence_chain as evidence_chain
from netcoop.core.inspector.render import explain_message as explain_message
from netcoop.core.inspector.render import load_view as load_view
from netcoop.core.inspector.render import render_json as render_json
from netcoop.core.inspector.render import render_sequence as render_sequence
from netcoop.core.inspector.render import render_table as render_table
from netcoop.core.inspector.render import summarize as summarize
from netcoop.core.inspector.render import to_data as to_data

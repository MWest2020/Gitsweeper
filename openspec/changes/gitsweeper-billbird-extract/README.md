# gitsweeper-billbird-extract

Decouple Gitsweeper from Billbird's REST shape. Remove the in-tree Billbird HTTP client and the 5 Billbird-touching MCP tools; route reconcile through the external billbird-client package as an optional dependency. Gitsweeper becomes Billbird-agnostic; the MCP registry shrinks to analytics-only tools.

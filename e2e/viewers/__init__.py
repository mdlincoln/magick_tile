"""Viewer backends: one adapter and one static page per IIIF client.

Each backend drives a different library against the same generated tree, so the
suite checks the tree rather than the quirks of a single viewer. ``base`` holds
the viewer-agnostic sweep and settle loop plus the request allowance table.
"""

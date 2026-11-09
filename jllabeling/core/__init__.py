"""Headless domain layer shared by the desktop UI and CLI helpers.

Modules in this package must not import PyQt.  UI code may import them; they
must never import UI code.
"""

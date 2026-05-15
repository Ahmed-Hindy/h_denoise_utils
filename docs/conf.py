# Configuration file for the Sphinx documentation builder.

import os
import sys

# Add the repository root (containing the h_denoise_utils package) to path.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Mock imports that may not be available
import unittest.mock as mock

sys.modules["hou"] = mock.MagicMock()
sys.modules["PyQt5"] = mock.MagicMock()
sys.modules["PyQt5.QtCore"] = mock.MagicMock()
sys.modules["PyQt5.QtGui"] = mock.MagicMock()
sys.modules["PyQt5.QtWidgets"] = mock.MagicMock()
sys.modules["PySide2"] = mock.MagicMock()
sys.modules["PySide2.QtCore"] = mock.MagicMock()
sys.modules["PySide2.QtGui"] = mock.MagicMock()
sys.modules["PySide2.QtWidgets"] = mock.MagicMock()

from h_denoise_utils import __version__

# -- Project information
project = "h_denoise_utils"
copyright = "2026, Ahmed Hindy"
author = "Ahmed Hindy"
release = __version__

# -- General configuration
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# -- Options for HTML output
html_theme = "sphinx_rtd_theme"
html_static_path = []  # Removed '_static' since it doesn't exist

# -- Extension configuration
autodoc_default_options = {
    "members": True,
    "member-order": "bysource",
    "special-members": "__init__",
    "undoc-members": True,
    "exclude-members": "__weakref__",
}

autodoc_mock_imports = ["hou", "PyQt5", "PySide2"]

napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = True

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}
